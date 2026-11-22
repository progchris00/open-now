"""Guarantees that hold even if a caller skips the service (S2-12.1).

The database refuses inconsistent money and duplicate idempotency keys,
placing an order is all-or-nothing, and the accept timer is only queued
once the order is committed.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

SAMPLE_ROW = {
    "items_total": Decimal("535.00"),
    "delivery_fee": Decimal("59.00"),
    "service_fee": Decimal("5.00"),
    "discount": Decimal("0.00"),
    "total": Decimal("599.00"),
    "bill": Decimal("1000.00"),
    "change": Decimal("401.00"),
}


def create_order_row(customer, **overrides):
    from orders.models import Order

    values = {
        "customer": customer,
        "shop_id": 1,
        "idempotency_key": uuid4().hex,
        "request_fingerprint": "0" * 64,
        **SAMPLE_ROW,
        **overrides,
    }
    return Order.objects.create(**values)


def assert_refused_by_database(customer, **overrides) -> None:
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        create_order_row(customer, **overrides)


# --- Database constraints ----------------------------------------------------------


def test_consistent_row_is_accepted(customer) -> None:
    order = create_order_row(customer)

    assert order.pk is not None


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param(
            {"bill": Decimal("598.99"), "change": Decimal("-0.01")},
            id="bill-below-total",
        ),
        pytest.param(
            {"total": Decimal("600.00"), "change": Decimal("400.00")},
            id="total-not-the-sum",
        ),
        pytest.param({"change": Decimal("400.00")}, id="change-not-bill-minus-total"),
        pytest.param(
            {
                "items_total": Decimal("-1.00"),
                "total": Decimal("63.00"),
                "change": Decimal("937.00"),
            },
            id="negative-items",
        ),
        pytest.param(
            {
                "discount": Decimal("700.00"),
                "total": Decimal("-101.00"),
                "change": Decimal("1101.00"),
            },
            id="negative-total",
        ),
        pytest.param({"payment_method": "gcash"}, id="not-cash"),
    ],
)
def test_database_refuses_inconsistent_money(customer, overrides) -> None:
    assert_refused_by_database(customer, **overrides)


def test_database_refuses_duplicate_idempotency_key(customer) -> None:
    key = uuid4().hex
    create_order_row(customer, idempotency_key=key)

    assert_refused_by_database(customer, idempotency_key=key)


def test_database_refuses_inconsistent_line_total(customer, menu) -> None:
    from django.db import IntegrityError, transaction

    from orders.models import OrderItem

    order = create_order_row(customer)
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderItem.objects.create(
            order=order,
            product=menu["rice"],
            name="Garlic rice",
            unit_price=Decimal("95.00"),
            quantity=3,
            line_total=Decimal("95.00"),
        )


def test_database_refuses_zero_quantity(customer, menu) -> None:
    from django.db import IntegrityError, transaction

    from orders.models import OrderItem

    order = create_order_row(customer)
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderItem.objects.create(
            order=order,
            product=menu["rice"],
            name="Garlic rice",
            unit_price=Decimal("95.00"),
            quantity=0,
            line_total=Decimal("0.00"),
        )


def test_products_with_orders_cannot_be_deleted(place, sample_request, menu) -> None:
    from django.db.models import ProtectedError

    assert place(sample_request).status_code == 201

    with pytest.raises(ProtectedError):
        menu["adobo"].delete()


# --- All or nothing ----------------------------------------------------------------


def place_sample(customer, menu, **overrides):
    from orders.services import CartLine, place_order

    values = {
        "customer": customer,
        "lines": [
            CartLine(product_id=menu["adobo"].pk, quantity=1),
            CartLine(product_id=menu["rice"].pk, quantity=3),
        ],
        "distance_km": Decimal("2"),
        "bill": Decimal("1000.00"),
        "payment_method": "cod",
        "idempotency_key": uuid4().hex,
        **overrides,
    }
    return place_order(**values)


def test_audit_failure_leaves_no_order_behind(customer, menu, monkeypatch) -> None:
    from orders import services
    from orders.models import Order, OrderItem, OrderStatusHistory

    def broken_record(**kwargs):
        raise RuntimeError("audit store is down")

    monkeypatch.setattr(services, "record", broken_record)

    with pytest.raises(RuntimeError):
        place_sample(customer, menu)

    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0
    assert OrderStatusHistory.objects.count() == 0


def test_service_returns_existing_order_on_replay(customer, menu) -> None:
    key = uuid4().hex

    first, first_created = place_sample(customer, menu, idempotency_key=key)
    again, again_created = place_sample(customer, menu, idempotency_key=key)

    assert (first_created, again_created) == (True, False)
    assert again.pk == first.pk


def test_lost_race_on_the_key_returns_the_winner(customer, menu, monkeypatch) -> None:
    """Two requests with the same key both pass the lookup; the database decides.

    The first request is committed (inside this test's savepoint) while the
    second one still believes the key is free, as happens when two requests
    arrive at the same time. The unique constraint makes the second insert fail
    and the service returns the first order instead of a second one.
    """
    from orders import services
    from orders.models import Order

    key = uuid4().hex
    winner, _ = place_sample(customer, menu, idempotency_key=key)

    real_lookup = services._existing_order
    calls = {"count": 0}

    def stale_lookup(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return real_lookup(*args, **kwargs)

    monkeypatch.setattr(services, "_existing_order", stale_lookup)

    loser, created = place_sample(customer, menu, idempotency_key=key)

    assert created is False
    assert loser.pk == winner.pk
    assert Order.objects.filter(idempotency_key=key).count() == 1


# --- After commit only ----------------------------------------------------------------


def test_accept_timer_queued_only_after_commit(
    customer, menu, set_settings, monkeypatch
) -> None:
    from django.test import TestCase

    from orders import tasks

    set_settings(accept_minutes=7)
    queued = []
    monkeypatch.setattr(
        tasks.accept_timer_expired,
        "apply_async",
        lambda **kwargs: queued.append(kwargs),
    )

    with TestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        order, _ = place_sample(customer, menu)

    assert queued == [], "queued before the transaction committed"
    assert len(callbacks) == 1

    callbacks[0]()

    assert queued == [{"args": [order.pk], "countdown": 7 * 60}]


def test_nothing_queued_when_the_order_rolls_back(customer, menu, monkeypatch) -> None:
    from django.db import transaction
    from django.test import TestCase

    from orders import services

    def broken_record(**kwargs):
        raise RuntimeError("audit store is down")

    monkeypatch.setattr(services, "record", broken_record)

    with TestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        with pytest.raises(RuntimeError), transaction.atomic():
            place_sample(customer, menu)

    assert callbacks == []


def test_replay_does_not_queue_a_second_timer(customer, menu) -> None:
    from django.test import TestCase

    key = uuid4().hex
    with TestCase.captureOnCommitCallbacks(execute=False) as first:
        place_sample(customer, menu, idempotency_key=key)
    with TestCase.captureOnCommitCallbacks(execute=False) as second:
        place_sample(customer, menu, idempotency_key=key)

    assert (len(first), len(second)) == (1, 0)


def test_accept_timer_task_leaves_the_order_for_s2_16(customer, menu) -> None:
    """S2-16.1 cancels unaccepted orders. Until then the task only reads it."""
    from orders.models import Order
    from orders.tasks import accept_timer_expired

    order, _ = place_sample(customer, menu)

    assert accept_timer_expired(order.pk) == Order.Status.NEW
    assert accept_timer_expired(987654321) is None
    order.refresh_from_db()
    assert order.status == Order.Status.NEW
