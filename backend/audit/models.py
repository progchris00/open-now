from django.conf import settings
from django.db import models, transaction


class ReadOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Audit records are read-only.")

    def delete(self):
        raise PermissionError("Audit records are read-only.")


class AuditLog(models.Model):
    objects = ReadOnlyQuerySet.as_manager()

    who = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_entries",
    )
    what = models.CharField(max_length=100)
    before = models.JSONField(blank=True, null=True)
    after = models.JSONField(blank=True, null=True)
    when = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-when", "-pk"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Audit entries are read-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit entries are read-only.")


class OrderQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if "status" in kwargs:
            raise PermissionError(
                "Order status changes must be saved with an actor."
            )
        return super().update(**kwargs)


class Order(models.Model):
    objects = OrderQuerySet.as_manager()

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        actor = kwargs.pop("actor", None)
        self._audit_actor = actor
        try:
            with transaction.atomic():
                return super().save(*args, **kwargs)
        finally:
            if hasattr(self, "_audit_actor"):
                del self._audit_actor


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Cash records are append-only.")

    def delete(self):
        raise PermissionError("Cash records are append-only.")

    def bulk_create(self, *args, **kwargs):
        raise PermissionError("Cash records must be created individually.")


class CashRecord(models.Model):
    objects = AppendOnlyQuerySet.as_manager()

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cash_records",
    )
    label = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Cash records are append-only.")

        with transaction.atomic():
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Cash records are append-only.")
