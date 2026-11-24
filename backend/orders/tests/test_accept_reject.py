"""The merchant accepts or rejects a New order (S2-15.1).

Rules:
- New -> Accepted and New -> Rejected are the only moves this task adds.
- Only a member of the order's shop may decide. Everyone else gets 403,
  whether or not the order exists.
- A decision after accept_minutes is refused; the deadline is read from
  admin settings each time it is checked.
- Repeating the same decision is safe: same answer, nothing written twice.
- Every decision writes one OrderStatusHistory row and one audit record, and
  queues the status-changed handoff only after the transaction commits.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from .conftest import OTHER_SHOP_ID, make_member


def accept_url(order_id: int) -> str:
    return f"/api/merchant/orders/{order_id}/accept"


def reject_url(order_id: int) -> str:
    return f"/api/merchant/orders/{order_id}/reject"


def make_old(order, minutes: float) -> None:
    """Pretend the order was placed this many minutes ago."""
    from django.utils import timezone

    from orders.models import Order

    Order.objects.filter(pk=order.pk).update(
        created_at=timezone.now() - timedelta(minutes=minutes)
    )
    order.refresh_from_db()


# --- The card's tests ---------------------------------------------------------


def test_accept_moves_to_accepted(api, merchant, new_order) -> None:
    from orders.models import Order

    response = api(merchant).post(accept_url(new_order.pk))

    assert response.status_code == 200, response.content
    assert response.json()["id"] == new_order.pk
    assert response.json()["status"] == "accepted"
    assert response.json()["reject_reason"] is None
    new_order.refresh_from_db()
    assert new_order.status == Order.Status.ACCEPTED


def test_reject_requires_reason(api, merchant, new_order) -> None:
    from orders.models import Order

    for body in ({}, {"reason": ""}, {"reason": "   "}):
        response = api(merchant).post(reject_url(new_order.pk), body, format="json")
        assert response.status_code == 400, body
        assert "reason" in response.json()

    new_order.refresh_from_db()
    assert new_order.status == Order.Status.NEW

    response = api(merchant).post(
        reject_url(new_order.pk), {"reason": "  Out of adobo  "}, format="json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "rejected"
    assert response.json()["reject_reason"] == "Out of adobo"


def test_only_own_shop_can_accept(
    api, merchant, other_merchant, customer, new_order
) -> None:
    from orders.models import Order

    for user in (other_merchant, customer, None):
        for url in (accept_url(new_order.pk), reject_url(new_order.pk)):
            response = api(user).post(url, {"reason": "x"}, format="json")
            assert response.status_code == 403, (user, url)

    new_order.refresh_from_db()
    assert new_order.status == Order.Status.NEW


def test_status_history_written(api, merchant, customer, new_order) -> None:
    api(merchant).post(
        reject_url(new_order.pk), {"reason": "Closed early"}, format="json"
    )

    rows = [
        (row.status, row.changed_by, row.reason)
        for row in new_order.status_history.all()
    ]
    assert rows == [("new", customer, ""), ("rejected", merchant, "Closed early")]
    assert all(row.changed_at is not None for row in new_order.status_history.all())


# --- What a reviewer would ask for --------------------------------------------


def test_accept_is_safe_to_retry(api, merchant, new_order) -> None:
    from audit.models import AuditLog

    first = api(merchant).post(accept_url(new_order.pk))
    second = api(merchant).post(accept_url(new_order.pk))

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert new_order.status_history.count() == 2
    assert (
        AuditLog.objects.filter(
            target_type="orders.order",
            target_id=str(new_order.pk),
            what="order.accepted",
        ).count()
        == 1
    )


def test_reject_is_safe_to_retry(api, merchant, new_order) -> None:
    body = {"reason": "Out of rice"}
    first = api(merchant).post(reject_url(new_order.pk), body, format="json")
    second = api(merchant).post(reject_url(new_order.pk), body, format="json")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert new_order.status_history.count() == 2


def test_reject_after_accept_is_409(api, merchant, new_order) -> None:
    from orders.models import Order

    api(merchant).post(accept_url(new_order.pk))
    response = api(merchant).post(
        reject_url(new_order.pk), {"reason": "Changed my mind"}, format="json"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "not_allowed"
    new_order.refresh_from_db()
    assert new_order.status == Order.Status.ACCEPTED
    assert new_order.status_history.count() == 2


def test_accept_after_reject_is_409(api, merchant, new_order) -> None:
    api(merchant).post(reject_url(new_order.pk), {"reason": "Closed"}, format="json")
    response = api(merchant).post(accept_url(new_order.pk))

    assert response.status_code == 409
    assert response.json()["code"] == "not_allowed"


def test_accept_after_deadline_is_refused(
    api, merchant, set_settings, new_order
) -> None:
    from orders.models import Order

    set_settings(accept_minutes=5)
    make_old(new_order, 5.5)

    for response in (
        api(merchant).post(accept_url(new_order.pk)),
        api(merchant).post(reject_url(new_order.pk), {"reason": "x"}, format="json"),
    ):
        assert response.status_code == 409
        assert response.json()["code"] == "deadline_passed"

    new_order.refresh_from_db()
    assert new_order.status == Order.Status.NEW
    assert new_order.status_history.count() == 1


def test_accept_just_before_deadline_is_allowed(
    merchant, set_settings, new_order
) -> None:
    from orders.transitions import accept_deadline, transition

    set_settings(accept_minutes=5)
    deadline = accept_deadline(new_order)

    order, changed = transition(
        order_id=new_order.pk, to="accepted", by=merchant, now=deadline
    )
    assert changed is True
    assert order.status == "accepted"


def test_deadline_follows_the_admin_setting(set_settings, new_order) -> None:
    from orders.transitions import accept_deadline

    set_settings(accept_minutes=5)
    assert accept_deadline(new_order) == new_order.created_at + timedelta(minutes=5)

    set_settings(accept_minutes=12)
    assert accept_deadline(new_order) == new_order.created_at + timedelta(minutes=12)


def test_other_shop_and_missing_order_look_the_same(
    api, other_merchant, new_order
) -> None:
    from orders.models import Order

    missing_id = (
        Order.objects.order_by("-pk").values_list("pk", flat=True).first()
    ) + 1000
    real = api(other_merchant).post(accept_url(new_order.pk))
    missing = api(other_merchant).post(accept_url(missing_id))

    assert real.status_code == missing.status_code == 403
    assert real.json() == missing.json()


def test_member_of_both_shops_can_decide(api, set_settings, new_order) -> None:
    from orders.models import ShopMember

    user = make_member(OTHER_SHOP_ID)
    ShopMember.objects.create(user=user, shop_id=new_order.shop_id)

    response = api(user).post(accept_url(new_order.pk))
    assert response.status_code == 200


def test_reason_length_is_limited(api, merchant, new_order) -> None:
    from orders.models import REJECT_REASON_MAX_LENGTH

    too_long = "x" * (REJECT_REASON_MAX_LENGTH + 1)
    response = api(merchant).post(
        reject_url(new_order.pk), {"reason": too_long}, format="json"
    )
    assert response.status_code == 400
    assert "reason" in response.json()


def test_audit_written_with_before_and_after(api, merchant, new_order) -> None:
    from audit.models import AuditLog

    api(merchant).post(reject_url(new_order.pk), {"reason": "Closed"}, format="json")

    entry = AuditLog.objects.get(
        target_type="orders.order", target_id=str(new_order.pk), what="order.rejected"
    )
    assert entry.who == merchant
    assert entry.before == {"status": "new"}
    assert entry.after == {"status": "rejected", "reason": "Closed"}


def test_audit_failure_leaves_status_unchanged(
    merchant, new_order, monkeypatch
) -> None:
    from django.db import transaction

    import orders.transitions
    from orders.models import Order

    def broken(**kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(orders.transitions, "record", broken)

    with pytest.raises(RuntimeError), transaction.atomic():
        orders.transitions.transition(order_id=new_order.pk, to="accepted", by=merchant)

    new_order.refresh_from_db()
    assert new_order.status == Order.Status.NEW
    assert new_order.status_history.count() == 1


def test_status_event_queued_only_after_commit(
    merchant, new_order, monkeypatch
) -> None:
    from django.test import TestCase

    import orders.notify
    from orders.transitions import transition

    sent = []
    monkeypatch.setattr(
        orders.notify,
        "order_status_changed",
        lambda order_id, status: sent.append((order_id, status)),
    )

    with TestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        transition(order_id=new_order.pk, to="accepted", by=merchant)
    assert sent == [], "queued before the transaction committed"

    for callback in callbacks:
        callback()
    assert sent == [(new_order.pk, "accepted")]


def test_retry_does_not_queue_a_second_event(merchant, new_order) -> None:
    from django.test import TestCase

    from orders.transitions import transition

    with TestCase.captureOnCommitCallbacks(execute=False):
        transition(order_id=new_order.pk, to="accepted", by=merchant)

    with TestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        _, changed = transition(order_id=new_order.pk, to="accepted", by=merchant)
    assert changed is False
    assert callbacks == []


def test_nothing_queued_when_the_decision_rolls_back(
    merchant, new_order, monkeypatch
) -> None:
    from django.db import transaction
    from django.test import TestCase

    import orders.transitions

    def broken_record(**kwargs):
        raise RuntimeError("audit store is down")

    monkeypatch.setattr(orders.transitions, "record", broken_record)

    with TestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        with pytest.raises(RuntimeError), transaction.atomic():
            orders.transitions.transition(
                order_id=new_order.pk, to="accepted", by=merchant
            )

    assert callbacks == []


def test_broker_outage_does_not_fail_a_decision(
    merchant, new_order, monkeypatch, caplog
) -> None:
    """The decision is committed before the event is queued, so a broker
    error is logged rather than turned into a failed request."""
    from django.test import TestCase

    import orders.tasks
    from orders.transitions import transition

    def down(*args, **kwargs):
        raise ConnectionError("redis is unreachable")

    monkeypatch.setattr(orders.tasks.order_status_changed, "delay", down)

    with TestCase.captureOnCommitCallbacks(execute=True):
        _, changed = transition(order_id=new_order.pk, to="accepted", by=merchant)

    assert changed is True
    new_order.refresh_from_db()
    assert new_order.status == "accepted"
    assert "redis is unreachable" in caplog.text


def test_status_event_task_reports_the_status(merchant, new_order) -> None:
    from orders.tasks import order_status_changed
    from orders.transitions import transition

    transition(order_id=new_order.pk, to="rejected", by=merchant, reason="Closed")
    assert order_status_changed.run(new_order.pk, "rejected") == "rejected"
    assert order_status_changed.run(new_order.pk + 10**9, "rejected") is None


def test_unknown_target_status_is_refused(merchant, new_order) -> None:
    from orders.transitions import TransitionError, transition

    with pytest.raises(TransitionError) as raised:
        transition(order_id=new_order.pk, to="new", by=merchant)
    assert raised.value.code == "not_allowed"


def test_reject_without_reason_refused_by_service(merchant, new_order) -> None:
    from orders.transitions import TransitionError, transition

    with pytest.raises(TransitionError) as raised:
        transition(order_id=new_order.pk, to="rejected", by=merchant, reason="  ")
    assert raised.value.code == "reason_required"


def test_database_refuses_rejected_row_without_reason(merchant, new_order) -> None:
    from django.db import IntegrityError, transaction

    from orders.models import OrderStatusHistory

    with pytest.raises(IntegrityError), transaction.atomic():
        OrderStatusHistory.objects.create(
            order=new_order, status="rejected", changed_by=merchant, reason=""
        )


def test_shop_member_describes_itself(merchant) -> None:
    from orders.models import ShopMember

    member = ShopMember.objects.get(user=merchant)
    assert str(member) == f"{merchant} @ shop {member.shop_id}"
