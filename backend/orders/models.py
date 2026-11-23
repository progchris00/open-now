"""Orders (S2-12.1).

An order is a promise of cash between the customer, the shop and the rider,
so the money on it is fixed when it is placed and the database itself refuses
numbers that don't add up:

    total  = items_total + delivery_fee + service_fee - discount
    change = bill - total,   bill >= total

Prices, the delivery fee and the service fee are copied onto the order, so a
later price or settings change never alters an order already placed.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import connection, models
from django.db.models import F, Q

MONEY = {"max_digits": 10, "decimal_places": 2}

# The largest amount a money column can hold: 99,999,999.99 for MONEY above.
MAX_PESOS = Decimal(10) ** (MONEY["max_digits"] - MONEY["decimal_places"]) - (
    Decimal(1).scaleb(-MONEY["decimal_places"])
)
# The largest OrderItem.quantity the database stores (2,147,483,647 on PostgreSQL).
MAX_QUANTITY = connection.ops.integer_field_range("PositiveIntegerField")[1]
IDEMPOTENCY_KEY_MAX_LENGTH = 100


class Product(models.Model):
    """TEMPORARY minimal product until the menu story (S2-08) adds the real one.

    shop_id is a plain number until the Shop model exists; S2-08 should
    replace this model and point OrderItem.product at its own Product.
    """

    shop_id = models.PositiveBigIntegerField()
    name = models.CharField(max_length=200)
    price = models.DecimalField(**MONEY)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0), name="orders_product_price_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"

    class PaymentMethod(models.TextChoices):
        CASH_ON_DELIVERY = "cod", "Cash on delivery"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    shop_id = models.PositiveBigIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH_ON_DELIVERY,
    )

    items_total = models.DecimalField(**MONEY)
    delivery_fee = models.DecimalField(**MONEY)
    service_fee = models.DecimalField(**MONEY)
    discount = models.DecimalField(**MONEY, default=0)
    total = models.DecimalField(**MONEY)
    bill = models.DecimalField(**MONEY)
    change = models.DecimalField(**MONEY)

    idempotency_key = models.CharField(max_length=IDEMPOTENCY_KEY_MAX_LENGTH)
    request_fingerprint = models.CharField(max_length=64)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "idempotency_key"],
                name="orders_order_one_order_per_key",
            ),
            models.CheckConstraint(
                condition=Q(payment_method="cod"),
                name="orders_order_cash_on_delivery_only",
            ),
            models.CheckConstraint(
                condition=Q(items_total__gte=0)
                & Q(delivery_fee__gte=0)
                & Q(service_fee__gte=0)
                & Q(discount__gte=0)
                & Q(total__gte=0),
                name="orders_order_amounts_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(
                    total=F("items_total")
                    + F("delivery_fee")
                    + F("service_fee")
                    - F("discount")
                ),
                name="orders_order_total_is_the_sum",
            ),
            models.CheckConstraint(
                condition=Q(bill__gte=F("total")),
                name="orders_order_bill_covers_total",
            ),
            models.CheckConstraint(
                condition=Q(change=F("bill") - F("total")),
                name="orders_order_change_is_bill_minus_total",
            ),
        ]

    def __str__(self) -> str:
        return f"Order {self.pk} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="order_items"
    )
    name = models.CharField(max_length=200)
    unit_price = models.DecimalField(**MONEY)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "product"], name="orders_item_one_line_per_product"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="orders_item_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="orders_item_price_not_negative"
            ),
            models.CheckConstraint(
                condition=Q(line_total=F("unit_price") * F("quantity")),
                name="orders_item_line_total_is_price_times_quantity",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.name}"


class OrderStatusHistory(models.Model):
    """One row per status an order enters, starting with New."""

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name="status_history"
    )
    status = models.CharField(max_length=20, choices=Order.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_status_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at", "pk"]

    def __str__(self) -> str:
        return f"Order {self.order_id} -> {self.status}"
