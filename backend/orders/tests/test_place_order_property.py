"""Properties of the order money (S2-12.1), checked with Hypothesis.

    total  = items + delivery + fee - discount
    change = bill - total, and the bill picked must be at least the total

The first two tests check the pure function the service uses. The last one
goes through POST /api/orders and checks the stored row, so the endpoint,
the serializer and the database constraints are covered too.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

pesos = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("99999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)
quantities = st.integers(min_value=1, max_value=50)
lines = st.lists(st.tuples(pesos, quantities), min_size=1, max_size=6)


@given(lines=lines, delivery=pesos, fee=pesos, extra=pesos)
@example(
    lines=[(Decimal("250.00"), 1), (Decimal("95.00"), 3)],
    delivery=Decimal("59.00"),
    fee=Decimal("5.00"),
    extra=Decimal("401.00"),
)
def test_totals_add_up_for_any_cart(lines, delivery, fee, extra) -> None:
    from orders.services import price_order

    items = sum((price * quantity for price, quantity in lines), Decimal("0"))
    bill = items + delivery + fee + extra

    totals = price_order(lines=lines, delivery_fee=delivery, service_fee=fee, bill=bill)

    assert totals.items_total == items
    assert totals.total == items + delivery + fee - totals.discount
    assert totals.change == bill - totals.total
    assert totals.change == extra
    assert all(
        line_total == price * quantity
        for (price, quantity), line_total in zip(lines, totals.line_totals, strict=True)
    )
    if lines == [(Decimal("250.00"), 1), (Decimal("95.00"), 3)]:
        assert (totals.items_total, totals.total, totals.change) == (
            Decimal("535.00"),
            Decimal("599.00"),
            Decimal("401.00"),
        )


@given(
    lines=lines, delivery=pesos, fee=pesos, short=pesos.filter(lambda value: value > 0)
)
@example(
    lines=[(Decimal("250.00"), 1), (Decimal("95.00"), 3)],
    delivery=Decimal("59.00"),
    fee=Decimal("5.00"),
    short=Decimal("0.01"),
)
def test_bill_below_total_always_rejected(lines, delivery, fee, short) -> None:
    from orders.services import BillTooSmall, price_order

    items = sum((price * quantity for price, quantity in lines), Decimal("0"))
    bill = items + delivery + fee - short

    with pytest.raises(BillTooSmall):
        price_order(lines=lines, delivery_fee=delivery, service_fee=fee, bill=bill)


@given(
    price=st.decimals(
        min_value=Decimal("0.01"), max_value=Decimal("99999.99"), places=2
    ),
    quantity=st.integers(min_value=1, max_value=2_147_483_647),
)
@example(price=Decimal("250.00"), quantity=1_000_000)
@example(price=Decimal("95.00"), quantity=1_052_000)
def test_amounts_either_fit_the_columns_or_are_refused(price, quantity) -> None:
    """No amount ever reaches the database that a money column can't hold."""
    from orders.models import MAX_PESOS
    from orders.services import OrderTooLarge, price_order

    line_total = price * quantity
    try:
        totals = price_order(
            lines=[(price, quantity)],
            delivery_fee=Decimal("59"),
            service_fee=Decimal("5"),
            bill=MAX_PESOS,
        )
    except OrderTooLarge:
        assert line_total + 64 > MAX_PESOS
    else:
        amounts = [*totals.line_totals, totals.items_total, totals.total]
        assert all(amount <= MAX_PESOS for amount in amounts)


def test_parts_that_fit_but_sum_too_large_are_refused() -> None:
    """Items and delivery each fit a column, but their total doesn't."""
    from orders.models import MAX_PESOS
    from orders.services import OrderTooLarge, price_order

    with pytest.raises(OrderTooLarge) as raised:
        price_order(
            lines=[(MAX_PESOS - Decimal("10"), 1)],
            delivery_fee=Decimal("59"),
            service_fee=Decimal("5"),
            bill=MAX_PESOS,
        )

    assert raised.value.field == "items"


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    prices=st.lists(
        st.decimals(min_value=Decimal("0.01"), max_value=Decimal("2000"), places=2),
        min_size=1,
        max_size=4,
    ),
    quantities=st.lists(quantities, min_size=4, max_size=4),
    km=st.decimals(min_value=Decimal("0"), max_value=Decimal("30"), places=3),
    fee=st.integers(min_value=0, max_value=50),
    extra=st.decimals(min_value=Decimal("0"), max_value=Decimal("5000"), places=2),
)
@example(
    prices=[Decimal("250.00"), Decimal("95.00")],
    quantities=[1, 3, 1, 1],
    km=Decimal("2"),
    fee=5,
    extra=Decimal("401.00"),
)
def test_stored_order_satisfies_the_money_equations(
    migrated_database, prices, quantities, km, fee, extra
) -> None:
    from django.db import transaction
    from rest_framework.test import APIClient

    from orders.models import Order, Product
    from settings_store.cache import invalidate_settings_cache
    from settings_store.models import Setting

    from .conftest import SAMPLE_SETTINGS, make_user

    invalidate_settings_cache()
    with transaction.atomic():
        for key, value in {**SAMPLE_SETTINGS, "service_fee_per_order": fee}.items():
            Setting.objects.filter(key=key).update(value=value)
        invalidate_settings_cache()

        products = [
            Product.objects.create(shop_id=1, name=f"Item {index}", price=price)
            for index, price in enumerate(prices)
        ]
        cart = [
            {"product_id": product.pk, "quantity": quantity}
            for product, quantity in zip(products, quantities, strict=False)
        ]
        items = sum(
            (
                product.price * quantity
                for product, quantity in zip(products, quantities, strict=False)
            ),
            Decimal("0"),
        )
        delivery = (Decimal("39") + Decimal("10") * km).quantize(Decimal("0.01"))
        expected_total = items + delivery + fee
        bill = expected_total + extra

        client = APIClient()
        client.force_authenticate(user=make_user(customer=True))
        response = client.post(
            "/api/orders",
            {
                "items": cart,
                "distance_km": str(km),
                "bill": str(bill),
                "payment_method": "cod",
            },
            format="json",
            headers={"Idempotency-Key": uuid4().hex},
        )

        assert response.status_code == 201, response.data
        order = Order.objects.get(pk=response.data["id"])
        assert order.items_total == items
        assert (
            order.total
            == order.items_total
            + order.delivery_fee
            + order.service_fee
            - order.discount
        )
        assert order.total == expected_total
        assert order.change == order.bill - order.total == extra
        assert sum(item.line_total for item in order.items.all()) == order.items_total
        assert order.status_history.count() == 1

        transaction.set_rollback(True)
    invalidate_settings_cache()
