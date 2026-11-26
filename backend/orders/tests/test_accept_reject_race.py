"""Accept and reject racing each other on real PostgreSQL (S2-15.1).

Two devices in one shop tap Accept and Reject at the same moment. Each runs
in its own thread with its own database connection, on rows that are really
committed, so the only thing that can keep them apart is the row lock taken
by transition(). Exactly one must win; the other must be told it lost.

Both threads are held inside the deadline check (after the status is read)
long enough to overlap. Without select_for_update() both read New and both
write, and this test fails: that is the evidence the lock does the work.

The test commits rows, so it cleans up after itself. Audit rows are
append-only through the ORM; cleanup removes this test's rows with a raw
delete, the one place that is allowed.
"""

from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest

from .conftest import SAMPLE_SHOP_ID

HOLD_SECONDS = 0.3


@pytest.fixture
def committed_order(migrated_database, monkeypatch):
    from decimal import Decimal

    from django.contrib.auth import get_user_model

    import orders.notify
    import orders.services

    # These rows really commit, so after-commit hooks really run. This test is
    # about the row lock, not the broker: keep both queue calls local.
    monkeypatch.setattr(orders.services, "_start_accept_timer", lambda order_id: None)
    monkeypatch.setattr(orders.notify, "order_status_changed", lambda *args: None)

    from audit.models import AuditLog
    from orders.models import Order, OrderItem, OrderStatusHistory, Product, ShopMember
    from orders.services import CartLine, place_order
    from settings_store.cache import invalidate_settings_cache

    invalidate_settings_cache()
    users = get_user_model().objects
    customer = users.create_user(username=f"race-customer-{uuid4().hex}")
    merchants = [
        users.create_user(username=f"race-merchant-{uuid4().hex}") for _ in range(2)
    ]
    for merchant in merchants:
        ShopMember.objects.create(user=merchant, shop_id=SAMPLE_SHOP_ID)
    product = Product.objects.create(
        shop_id=SAMPLE_SHOP_ID, name="Race adobo", price=Decimal("250.00")
    )
    order, _ = place_order(
        customer=customer,
        lines=[CartLine(product_id=product.pk, quantity=1)],
        distance_km=Decimal("2"),
        bill=Decimal("1000.00"),
        payment_method="cod",
        idempotency_key=uuid4().hex,
    )

    yield order, merchants

    AuditLog.objects.filter(
        target_type="orders.order", target_id=str(order.pk)
    )._raw_delete(AuditLog.objects.db)
    OrderStatusHistory.objects.filter(order=order).delete()
    OrderItem.objects.filter(order=order).delete()
    Order.objects.filter(pk=order.pk).delete()
    product.delete()
    ShopMember.objects.filter(user__in=merchants).delete()
    for user in [customer, *merchants]:
        user.delete()
    invalidate_settings_cache()


def test_accept_and_reject_race_has_one_winner(committed_order, monkeypatch) -> None:
    from django.db import connection

    import orders.transitions
    from orders.models import Order
    from orders.transitions import TransitionError, transition

    order, (first, second) = committed_order
    real_deadline = orders.transitions.accept_deadline

    def slow_deadline(o):
        time.sleep(HOLD_SECONDS)
        return real_deadline(o)

    monkeypatch.setattr(orders.transitions, "accept_deadline", slow_deadline)

    start = threading.Barrier(2)
    results: dict[str, object] = {}

    def decide(name, to, by, reason=""):
        try:
            start.wait()
            transition(order_id=order.pk, to=to, by=by, reason=reason)
            results[name] = "won"
        except TransitionError as error:
            results[name] = error.code
        finally:
            connection.close()

    threads = [
        threading.Thread(target=decide, args=("accept", "accepted", first)),
        threading.Thread(target=decide, args=("reject", "rejected", second, "Closed")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(results.values()) == ["not_allowed", "won"], results
    winner = "accepted" if results["accept"] == "won" else "rejected"

    final = Order.objects.get(pk=order.pk)
    assert final.status == winner
    assert [row.status for row in final.status_history.all()] == ["new", winner]
