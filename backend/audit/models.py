from django.conf import settings
from django.core.exceptions import ValidationError
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
        update_fields = kwargs.get("update_fields")
        with transaction.atomic():
            if not self._state.adding:
                previous = type(self).objects.select_for_update().get(pk=self.pk)
                before = previous.status
            else:
                before = None

            status_is_saved = update_fields is None or "status" in update_fields
            status_changed = before is not None and before != self.status
            if status_changed and not status_is_saved:
                status_changed = False
            if status_changed and actor is None:
                raise PermissionError("Order status changes require an actor.")
            if self.status not in self.Status.values:
                raise ValidationError({"status": "Invalid order status."})

            super().save(*args, **kwargs)
            if status_changed:
                AuditLog.objects.create(
                    who=actor,
                    what="order.status",
                    before=before,
                    after=self.status,
                )


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
            super().save(*args, **kwargs)
            AuditLog.objects.create(
                who=self.actor,
                what="cash.record",
                before=None,
                after=self.label,
            )

    def delete(self, *args, **kwargs):
        raise PermissionError("Cash records are append-only.")
