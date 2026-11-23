"""place_order: a customer's cash-on-delivery order is placed (S2-12.1).

The HTTP endpoint, POST /api/orders, comes with S2-11, once the delivery
distance can come from checked delivery details instead of the request.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from .conftest import make_customer


def refused(place, field: str, **overrides) -> None:
    from orders.services import PlacementError

    with pytest.raises(PlacementError) as raised:
        place(**overrides)
    assert raised.value.field == field


# --- The card's tests ---------------------------------------------------------


def test_place_order_creates_new_status(place, customer) -> None:
    from audit.models import AuditLog
    from orders.models import Order

    order, created = place()

    assert created is True
    assert order.status == Order.Status.NEW
    assert order.customer == customer

    history = list(order.status_history.all())
    assert [(row.status, row.changed_by) for row in history] == [
        (Order.Status.NEW, customer)
    ]

    entry = AuditLog.objects.get(target_type="orders.order", target_id=str(order.pk))
    assert entry.what == "order.placed"
    assert entry.who == customer
    assert entry.before is None
    assert entry.after["status"] == "new"
    assert entry.after["total"] == "599.00"
    assert entry.after["bill"] == "1000.00"
    assert entry.after["change"] == "401.00"


def test_sample_order_totals(place) -> None:
    order, _ = place()
    order.refresh_from_db()

    assert order.items_total == Decimal("535.00")
    assert order.delivery_fee == Decimal("59.00")
    assert order.service_fee == Decimal("5.00")
    assert order.discount == Decimal("0.00")
    assert order.total == Decimal("599.00")


def test_change_from_bill(place) -> None:
    order, _ = place()
    order.refresh_from_db()

    assert order.bill == Decimal("1000.00")
    assert order.change == Decimal("401.00")


def test_bill_below_total_rejected(new_orders, place) -> None:
    refused(place, "bill", bill=Decimal("598.99"))

    assert new_orders() == 0


def test_bill_equal_to_total_is_accepted(place) -> None:
    order, _ = place(bill=Decimal("599.00"))

    assert order.change == Decimal("0.00")


@pytest.mark.parametrize("method", ["gcash", "card", "COD", ""])
def test_only_cod_accepted(new_orders, place, method) -> None:
    refused(place, "payment_method", payment_method=method)

    assert new_orders() == 0


def test_payment_method_read_from_settings(place, set_settings) -> None:
    """The accepted method is the payment_method setting, not a literal."""
    set_settings(payment_method="none")

    refused(place, "payment_method")


# --- The money comes from the server --------------------------------------------


def test_prices_come_from_the_products(place, menu) -> None:
    order, _ = place()

    lines = sorted(order.items.all(), key=lambda line: line.name)
    assert [
        (line.name, line.unit_price, line.quantity, line.line_total) for line in lines
    ] == [
        ("Chicken adobo", Decimal("250.00"), 1, Decimal("250.00")),
        ("Garlic rice", Decimal("95.00"), 3, Decimal("285.00")),
    ]


def test_service_fee_read_from_settings(place, set_settings) -> None:
    set_settings(service_fee_per_order=7.5)

    order, _ = place()

    assert order.service_fee == Decimal("7.50")
    assert order.total == Decimal("601.50")
    assert order.change == Decimal("398.50")


def test_delivery_fee_read_from_settings(place, set_settings) -> None:
    set_settings(delivery_base_fee=20, delivery_per_km=15)

    order, _ = place()

    assert order.delivery_fee == Decimal("50.00")
    assert order.total == Decimal("590.00")


def test_fee_and_prices_are_snapshotted(place, set_settings, menu) -> None:
    from orders.models import Order

    placed, _ = place()

    set_settings(service_fee_per_order=50, delivery_base_fee=100)
    menu["adobo"].price = Decimal("999.00")
    menu["adobo"].save()

    order = Order.objects.get(pk=placed.pk)
    assert order.service_fee == Decimal("5.00")
    assert order.delivery_fee == Decimal("59.00")
    assert order.total == Decimal("599.00")
    assert order.items.get(product=menu["adobo"]).unit_price == Decimal("250.00")


def test_money_columns_are_decimal_pesos() -> None:
    from django.db import models

    from orders.models import Order, OrderItem

    for model, names in [
        (
            Order,
            [
                "items_total",
                "delivery_fee",
                "service_fee",
                "discount",
                "total",
                "bill",
                "change",
            ],
        ),
        (OrderItem, ["unit_price", "line_total"]),
    ]:
        for name in names:
            field = model._meta.get_field(name)
            assert isinstance(field, models.DecimalField), name
            assert field.decimal_places == 2, name


def test_there_is_no_order_endpoint_yet(migrated_database) -> None:
    """POST /api/orders waits for S2-11, so the distance can't be sent by the
    customer (review on #20)."""
    from django.urls import Resolver404, resolve

    with pytest.raises(Resolver404):
        resolve("/api/orders")


# --- Bad carts --------------------------------------------------------------------


def test_empty_cart_rejected(place) -> None:
    refused(place, "items", lines=[])


def test_unknown_product_rejected(new_orders, place) -> None:
    from orders.services import CartLine

    refused(place, "items", lines=[CartLine(product_id=987654321, quantity=1)])

    assert new_orders() == 0


@pytest.mark.parametrize("quantity", [0, -1])
def test_quantity_must_be_positive(place, menu, quantity) -> None:
    from orders.services import CartLine

    refused(place, "items", lines=[CartLine(menu["adobo"].pk, quantity)])


def test_order_too_large_for_the_money_columns_is_refused(
    new_orders, place, menu
) -> None:
    """₱250 x 1,000,000 = ₱250,000,000.00, more than a money column holds."""
    from orders.services import CartLine

    refused(place, "items", lines=[CartLine(menu["adobo"].pk, 1_000_000)])

    assert new_orders() == 0


def test_largest_order_that_fits_is_accepted(place, menu) -> None:
    """₱95 x 1,052,000 = ₱99,940,000 of items, just under the column limit."""
    from orders.services import CartLine

    order, _ = place(
        lines=[CartLine(menu["rice"].pk, 1_052_000)], bill=Decimal("99999999.99")
    )

    assert order.items_total == Decimal("99940000.00")


def test_bill_too_large_for_the_money_columns_is_refused(new_orders, place) -> None:
    refused(place, "bill", bill=Decimal("100000000.00"))

    assert new_orders() == 0


def test_quantity_above_the_column_range_is_refused(place) -> None:
    """A ₱0.01 item keeps the money small, so only the quantity overflows."""
    from django.db import connection

    from orders.models import Product
    from orders.services import CartLine

    _, largest = connection.ops.integer_field_range("PositiveIntegerField")
    cheap = Product.objects.create(shop_id=1, name="Candy", price=Decimal("0.01"))

    refused(
        place,
        "items",
        lines=[CartLine(cheap.pk, largest + 1)],
        bill=Decimal("99999999.99"),
    )


def test_delivery_fee_too_large_is_refused(place, set_settings) -> None:
    set_settings(delivery_per_km=99_999)

    refused(
        place,
        "distance_km",
        distance_km=Decimal("9999.999"),
        bill=Decimal("99999999.99"),
    )


def test_same_product_twice_rejected(place, menu) -> None:
    from orders.services import CartLine

    line = CartLine(menu["adobo"].pk, 1)

    refused(place, "items", lines=[line, line])


def test_items_from_two_shops_rejected(place, sample_order) -> None:
    from orders.models import Product
    from orders.services import CartLine

    other = Product.objects.create(shop_id=2, name="Halo-halo", price=Decimal("80.00"))

    refused(place, "items", lines=[*sample_order["lines"], CartLine(other.pk, 1)])


def test_negative_distance_rejected(place) -> None:
    refused(place, "distance_km", distance_km=Decimal("-1"))


def test_order_records_the_shop(place, menu) -> None:
    order, _ = place()

    assert order.shop_id == menu["adobo"].shop_id


# --- Placing twice ----------------------------------------------------------------


def test_double_submit_creates_one_order(new_orders, place) -> None:
    key = uuid4().hex

    first, first_created = place(idempotency_key=key)
    second, second_created = place(idempotency_key=key)

    assert (first_created, second_created) == (True, False)
    assert second.pk == first.pk
    assert new_orders() == 1


def test_same_key_with_a_different_order_is_refused(new_orders, place) -> None:
    from orders.services import KeyReused

    key = uuid4().hex
    place(idempotency_key=key)

    with pytest.raises(KeyReused):
        place(idempotency_key=key, bill=Decimal("600.00"))

    assert new_orders() == 1


def test_idempotency_key_is_per_customer(place) -> None:
    key = uuid4().hex

    first, _ = place(idempotency_key=key)
    second, created = place(idempotency_key=key, customer=make_customer())

    assert created is True
    assert first.pk != second.pk


@pytest.mark.parametrize("key", ["", "x" * 101])
def test_idempotency_key_must_fit(new_orders, place, key) -> None:
    refused(place, "idempotency_key", idempotency_key=key)

    assert new_orders() == 0
