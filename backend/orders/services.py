"""Placing a cash-on-delivery order (S2-12.1).

The server works out every amount itself: prices come from the products,
the delivery fee from pricing.delivery_fee and the admin settings, the
service fee from service_fee_per_order. Whatever money the client sends is
ignored.

Placing is all-or-nothing: the order, its items, the first status row and
the audit entry are written in one transaction. The accept timer is queued
only after that transaction commits.

Each customer's Idempotency-Key places at most one order. Sending the same
order again with the same key returns the first order; sending a different
order with a key already used is a conflict. The unique constraint on
(customer, idempotency_key) settles two requests that arrive together.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction

from audit.log import record
from pricing.delivery_fee import delivery_fee_for_km
from settings_store.cache import get_setting

from .cash import change_due, order_total, to_peso
from .models import MAX_PESOS, Order, OrderItem, OrderStatusHistory, Product


class PlacementError(ValueError):
    """The order can't be placed. `field` names the request field at fault."""

    field = "non_field_errors"

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        if field is not None:
            self.field = field


class BillTooSmall(PlacementError):
    field = "bill"


class OrderTooLarge(PlacementError):
    """An amount wouldn't fit the order's money columns."""

    field = "items"


class KeyReused(Exception):
    """The Idempotency-Key was already used for a different order."""


@dataclass(frozen=True)
class CartLine:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Totals:
    line_totals: tuple[Decimal, ...]
    items_total: Decimal
    delivery_fee: Decimal
    service_fee: Decimal
    discount: Decimal
    total: Decimal
    bill: Decimal
    change: Decimal


def price_order(
    *,
    lines: Sequence[tuple[Decimal, int]],
    delivery_fee: Decimal,
    service_fee: Decimal,
    bill: Decimal,
    discount: Decimal = Decimal("0"),
) -> Totals:
    """Work out an order's money from (unit price, quantity) lines.

    Raises OrderTooLarge when an amount wouldn't fit a money column, and
    BillTooSmall when the bill is below the total. Size is checked first, so
    a huge order gets a clear message instead of an impossible bill.
    """
    line_totals = tuple(to_peso(price * quantity) for price, quantity in lines)
    items_total = sum(line_totals, Decimal("0"))
    if items_total > MAX_PESOS:
        raise OrderTooLarge(f"Orders can't be more than ₱{MAX_PESOS:,.2f}.")
    if to_peso(delivery_fee) > MAX_PESOS:
        raise OrderTooLarge(
            "The delivery fee for this distance is too large.", field="distance_km"
        )
    total = order_total(items_total, delivery_fee, service_fee, discount=discount)
    if total > MAX_PESOS:
        raise OrderTooLarge(f"Orders can't be more than ₱{MAX_PESOS:,.2f}.")
    try:
        change = change_due(bill=bill, total=total)
    except ValueError as error:
        raise BillTooSmall(
            f"The bill must be at least the total of ₱{total:,.2f}."
        ) from error
    return Totals(
        line_totals=line_totals,
        items_total=items_total,
        delivery_fee=to_peso(delivery_fee),
        service_fee=to_peso(service_fee),
        discount=to_peso(discount),
        total=total,
        bill=to_peso(bill),
        change=change,
    )


def fingerprint(
    *,
    lines: Sequence[CartLine],
    distance_km: Decimal,
    bill: Decimal,
    payment_method: str,
) -> str:
    """A hash of what the customer asked for, to recognise a repeated request."""
    canonical = {
        "lines": sorted((line.product_id, line.quantity) for line in lines),
        "distance_km": str(Decimal(distance_km).normalize()),
        "bill": str(to_peso(bill)),
        "payment_method": payment_method,
    }
    encoded = json.dumps(canonical, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _existing_order(customer, idempotency_key: str) -> Order | None:
    return Order.objects.filter(
        customer=customer, idempotency_key=idempotency_key
    ).first()


def _replay(order: Order, request_fingerprint: str) -> tuple[Order, bool]:
    if order.request_fingerprint != request_fingerprint:
        raise KeyReused("This Idempotency-Key was already used for another order.")
    return order, False


def _load_products(lines: Sequence[CartLine]) -> list[Product]:
    if not lines:
        raise PlacementError("The cart is empty.", field="items")

    ids = [line.product_id for line in lines]
    if len(set(ids)) != len(ids):
        raise PlacementError("Each product can only be listed once.", field="items")
    if any(line.quantity <= 0 for line in lines):
        raise PlacementError("Quantities must be at least 1.", field="items")

    products = Product.objects.in_bulk(ids)
    missing = [product_id for product_id in ids if product_id not in products]
    if missing:
        raise PlacementError(f"Unknown products: {missing}.", field="items")

    shops = {product.shop_id for product in products.values()}
    if len(shops) != 1:
        raise PlacementError("All items must come from one shop.", field="items")

    return [products[product_id] for product_id in ids]


def place_order(
    *,
    customer,
    lines: Sequence[CartLine],
    distance_km: Decimal,
    bill: Decimal,
    payment_method: str,
    idempotency_key: str,
) -> tuple[Order, bool]:
    """Place the order. Returns (order, created).

    created is False when the same request was already placed with this key.
    Raises PlacementError for a bad request and KeyReused for a key that was
    used for a different order.
    """
    request_fingerprint = fingerprint(
        lines=lines,
        distance_km=distance_km,
        bill=bill,
        payment_method=payment_method,
    )

    existing = _existing_order(customer, idempotency_key)
    if existing is not None:
        return _replay(existing, request_fingerprint)

    if payment_method != get_setting("payment_method"):
        raise PlacementError(
            "Only cash on delivery is accepted.", field="payment_method"
        )
    if distance_km < 0:
        raise PlacementError("Distance cannot be negative.", field="distance_km")

    products = _load_products(lines)
    totals = price_order(
        lines=[
            (product.price, line.quantity)
            for product, line in zip(products, lines, strict=True)
        ],
        delivery_fee=delivery_fee_for_km(
            distance_km,
            base_fee=get_setting("delivery_base_fee"),
            per_km=get_setting("delivery_per_km"),
        ),
        service_fee=to_peso(get_setting("service_fee_per_order")),
        bill=bill,
    )

    try:
        with transaction.atomic():
            order = _create(
                customer=customer,
                products=products,
                lines=lines,
                totals=totals,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
    except IntegrityError:
        # Another request with the same key committed first.
        winner = _existing_order(customer, idempotency_key)
        if winner is None:
            raise
        return _replay(winner, request_fingerprint)

    return order, True


def _create(
    *,
    customer,
    products: Sequence[Product],
    lines: Sequence[CartLine],
    totals: Totals,
    idempotency_key: str,
    request_fingerprint: str,
) -> Order:
    order = Order.objects.create(
        customer=customer,
        shop_id=products[0].shop_id,
        status=Order.Status.NEW,
        items_total=totals.items_total,
        delivery_fee=totals.delivery_fee,
        service_fee=totals.service_fee,
        discount=totals.discount,
        total=totals.total,
        bill=totals.bill,
        change=totals.change,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )
    OrderItem.objects.bulk_create(
        OrderItem(
            order=order,
            product=product,
            name=product.name,
            unit_price=product.price,
            quantity=line.quantity,
            line_total=line_total,
        )
        for product, line, line_total in zip(
            products, lines, totals.line_totals, strict=True
        )
    )
    OrderStatusHistory.objects.create(
        order=order, status=Order.Status.NEW, changed_by=customer
    )
    record(
        who=customer,
        what="order.placed",
        target=order,
        after={
            "status": order.status,
            "shop_id": order.shop_id,
            "items_total": str(order.items_total),
            "delivery_fee": str(order.delivery_fee),
            "service_fee": str(order.service_fee),
            "discount": str(order.discount),
            "total": str(order.total),
            "bill": str(order.bill),
            "change": str(order.change),
        },
    )
    # robust: the order is already committed, so a broker outage is logged
    # instead of turning a placed order into a 500 for the customer.
    transaction.on_commit(lambda: _start_accept_timer(order.pk), robust=True)
    return order


def _start_accept_timer(order_id: int) -> None:
    from .tasks import accept_timer_expired

    accept_timer_expired.apply_async(
        args=[order_id], countdown=int(get_setting("accept_minutes")) * 60
    )
