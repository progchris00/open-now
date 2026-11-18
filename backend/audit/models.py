from django.conf import settings
from django.db import models, transaction


class AuditLog(models.Model):
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
        ordering = ["-when"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Audit entries are read-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit entries are read-only.")


class Order(models.Model):
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
        with transaction.atomic():
            if self.pk:
                if not actor:
                    raise PermissionError("Order changes require an actor.")
                previous = type(self).objects.select_for_update().get(pk=self.pk)
                before = previous.status
            else:
                before = None

            super().save(*args, **kwargs)
            if before is not None and before != self.status:
                AuditLog.objects.create(
                    who=actor,
                    what="order.status",
                    before=before,
                    after=self.status,
                )


class CashRecord(models.Model):
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
