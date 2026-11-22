"""POST /api/orders: a customer places a cash-on-delivery order (S2-12.1)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from .conftest import make_user


def order_count() -> int:
    from orders.models import Order

    return Order.objects.count()


# --- The card's tests ---------------------------------------------------------


def test_place_order_creates_new_status(place, sample_request, customer) -> None:
    from audit.models import AuditLog
    from orders.models import Order

    response = place(sample_request)

    assert response.status_code == 201, response.data
    order = Order.objects.get(pk=response.data["id"])
    assert response.data["status"] == "new"
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


def test_sample_order_totals(place, sample_request) -> None:
    response = place(sample_request)

    assert response.status_code == 201, response.data
    assert response.data["items_total"] == "535.00"
    assert response.data["delivery_fee"] == "59.00"
    assert response.data["service_fee"] == "5.00"
    assert response.data["discount"] == "0.00"
    assert response.data["total"] == "599.00"


def test_change_from_bill(place, sample_request) -> None:
    response = place(sample_request)

    assert response.status_code == 201, response.data
    assert response.data["bill"] == "1000.00"
    assert response.data["change"] == "401.00"


def test_bill_below_total_rejected(place, sample_request) -> None:
    response = place({**sample_request, "bill": "598.99"})

    assert response.status_code == 400
    assert "bill" in response.data
    assert order_count() == 0


def test_bill_equal_to_total_is_accepted(place, sample_request) -> None:
    response = place({**sample_request, "bill": "599.00"})

    assert response.status_code == 201, response.data
    assert response.data["change"] == "0.00"


@pytest.mark.parametrize("method", ["gcash", "card", "COD", "", None])
def test_only_cod_accepted(place, sample_request, method) -> None:
    response = place({**sample_request, "payment_method": method})

    assert response.status_code == 400
    assert "payment_method" in response.data
    assert order_count() == 0


def test_missing_payment_method_rejected(place, sample_request) -> None:
    body = {
        key: value for key, value in sample_request.items() if key != "payment_method"
    }

    response = place(body)

    assert response.status_code == 400
    assert "payment_method" in response.data


# --- The server works the money out itself --------------------------------------


def test_client_sent_prices_are_ignored(place, sample_request) -> None:
    body = {
        **sample_request,
        "items": [{**line, "unit_price": "1.00"} for line in sample_request["items"]],
        "total": "1.00",
        "delivery_fee": "0.00",
        "service_fee": "0.00",
        "change": "999.00",
    }

    response = place(body)

    assert response.status_code == 201, response.data
    assert response.data["total"] == "599.00"
    assert response.data["change"] == "401.00"


def test_order_items_store_name_price_and_line_total(place, sample_request) -> None:
    response = place(sample_request)

    assert response.status_code == 201, response.data
    lines = sorted(response.data["items"], key=lambda line: line["name"])
    assert [
        (line["name"], line["unit_price"], line["quantity"], line["line_total"])
        for line in lines
    ] == [
        ("Chicken adobo", "250.00", 1, "250.00"),
        ("Garlic rice", "95.00", 3, "285.00"),
    ]


def test_service_fee_read_from_settings(place, sample_request, set_settings) -> None:
    set_settings(service_fee_per_order=7.5)

    response = place(sample_request)

    assert response.status_code == 201, response.data
    assert response.data["service_fee"] == "7.50"
    assert response.data["total"] == "601.50"
    assert response.data["change"] == "398.50"


def test_delivery_fee_read_from_settings(place, sample_request, set_settings) -> None:
    set_settings(delivery_base_fee=20, delivery_per_km=15)

    response = place(sample_request)

    assert response.status_code == 201, response.data
    assert response.data["delivery_fee"] == "50.00"
    assert response.data["total"] == "590.00"


def test_payment_method_read_from_settings(place, sample_request, set_settings) -> None:
    """The accepted method is the payment_method setting, not a literal."""
    from settings_store.cache import invalidate_settings_cache
    from settings_store.models import Setting

    Setting.objects.filter(key="payment_method").update(value="none")
    invalidate_settings_cache()

    response = place(sample_request)

    assert response.status_code == 400
    assert "payment_method" in response.data


def test_fee_and_prices_are_snapshotted(
    place, sample_request, set_settings, menu
) -> None:
    from orders.models import Order

    response = place(sample_request)
    assert response.status_code == 201, response.data

    set_settings(service_fee_per_order=50, delivery_base_fee=100)
    menu["adobo"].price = Decimal("999.00")
    menu["adobo"].save()

    order = Order.objects.get(pk=response.data["id"])
    assert order.service_fee == Decimal("5.00")
    assert order.delivery_fee == Decimal("59.00")
    assert order.total == Decimal("599.00")
    assert order.items.get(product=menu["adobo"]).unit_price == Decimal("250.00")


def test_money_is_decimal_end_to_end(place, sample_request) -> None:
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

    response = place(sample_request)
    for name in [
        "items_total",
        "delivery_fee",
        "service_fee",
        "total",
        "bill",
        "change",
    ]:
        assert isinstance(response.data[name], str), name


# --- Bad carts --------------------------------------------------------------------


def test_empty_cart_rejected(place, sample_request) -> None:
    response = place({**sample_request, "items": []})

    assert response.status_code == 400
    assert "items" in response.data


def test_unknown_product_rejected(place, sample_request) -> None:
    body = {**sample_request, "items": [{"product_id": 987654321, "quantity": 1}]}

    response = place(body)

    assert response.status_code == 400
    assert "items" in response.data
    assert order_count() == 0


@pytest.mark.parametrize("quantity", [0, -1])
def test_quantity_must_be_positive(place, sample_request, quantity) -> None:
    line = {**sample_request["items"][0], "quantity": quantity}

    response = place({**sample_request, "items": [line]})

    assert response.status_code == 400


def test_same_product_twice_rejected(place, sample_request) -> None:
    line = sample_request["items"][0]

    response = place({**sample_request, "items": [line, line]})

    assert response.status_code == 400
    assert "items" in response.data


def test_items_from_two_shops_rejected(place, sample_request, menu) -> None:
    from orders.models import Product

    other = Product.objects.create(shop_id=2, name="Halo-halo", price=Decimal("80.00"))
    body = {
        **sample_request,
        "items": [*sample_request["items"], {"product_id": other.pk, "quantity": 1}],
    }

    response = place(body)

    assert response.status_code == 400
    assert "items" in response.data


def test_negative_distance_rejected(place, sample_request) -> None:
    response = place({**sample_request, "distance_km": "-1"})

    assert response.status_code == 400
    assert "distance_km" in response.data


def test_order_records_the_shop(place, sample_request, menu) -> None:
    response = place(sample_request)

    assert response.status_code == 201, response.data
    assert response.data["shop_id"] == menu["adobo"].shop_id


# --- Who may call it --------------------------------------------------------------


def test_non_customer_gets_403(place, sample_request) -> None:
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=make_user(customer=False))

    response = place(sample_request, client=client)

    assert response.status_code == 403
    assert order_count() == 0


def test_anonymous_gets_403(place, sample_request) -> None:
    from rest_framework.test import APIClient

    response = place(sample_request, client=APIClient())

    assert response.status_code == 403
    assert order_count() == 0


# --- Placing twice ----------------------------------------------------------------


def test_double_submit_creates_one_order(place, sample_request) -> None:
    key = uuid4().hex

    first = place(sample_request, key=key)
    second = place(sample_request, key=key)

    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert second.data == first.data
    assert order_count() == 1


def test_same_key_with_a_different_order_is_409(place, sample_request) -> None:
    key = uuid4().hex

    first = place(sample_request, key=key)
    second = place({**sample_request, "bill": "600.00"}, key=key)

    assert first.status_code == 201, first.data
    assert second.status_code == 409
    assert order_count() == 1


def test_idempotency_key_is_per_customer(place, sample_request) -> None:
    from rest_framework.test import APIClient

    other = APIClient()
    other.force_authenticate(user=make_user(customer=True))
    key = uuid4().hex

    first = place(sample_request, key=key)
    second = place(sample_request, key=key, client=other)

    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    assert first.data["id"] != second.data["id"]


@pytest.mark.parametrize("key", [None, "", "x" * 101])
def test_idempotency_key_required_and_bounded(
    customer_client, sample_request, key
) -> None:
    headers = {} if key is None else {"Idempotency-Key": key}

    response = customer_client.post(
        "/api/orders", sample_request, format="json", headers=headers
    )

    assert response.status_code == 400
    assert "idempotency_key" in response.data
    assert order_count() == 0
