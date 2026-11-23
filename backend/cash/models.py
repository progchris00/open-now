from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from orders.models import MONEY, Order


class ReadOnlyCashQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Cash records are read-only.")

    def delete(self):
        raise PermissionError("Cash records are read-only.")


class CashRecord(models.Model):
    class Type(models.TextChoices):
        CUSTOMER_PAYMENT = "customer_payment", "Customer payment"
        CHANGE = "change", "Change"
        SHOP_PAYOUT = "shop_payout", "Shop payout"
        DELIVERY_PAYMENT = "delivery_payment", "Delivery payment"
        CORRECTION = "correction", "Correction"

    class Party(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        RIDER = "rider", "Rider"
        SHOP = "shop", "Shop"
        PLATFORM = "platform", "Platform"
        COORDINATOR = "coordinator", "Area coordinator"

    objects = ReadOnlyCashQuerySet.as_manager()

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="cash_records",
    )
    type = models.CharField(max_length=30, choices=Type.choices)
    amount = models.DecimalField(**MONEY)
    from_party = models.CharField(
        max_length=20,
        choices=Party.choices,
        db_column="from",
    )
    to_party = models.CharField(
        max_length=20,
        choices=Party.choices,
        db_column="to",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cash_records_created",
    )
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="cash_record_amount_positive",
            ),
            models.CheckConstraint(
                condition=~Q(from_party=F("to_party")),
                name="cash_record_parties_differ",
            ),
            models.CheckConstraint(
                condition=~Q(type="correction") | ~Q(reason=""),
                name="cash_correction_has_reason",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Cash records are read-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Cash records are read-only.")

    def __str__(self) -> str:
        return f"{self.type}: {self.from_party} -> {self.to_party} {self.amount}"
