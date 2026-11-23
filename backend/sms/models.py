from django.db import models


class SmsLog(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RETRYING = "retrying", "Retrying"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    event_key = models.CharField(max_length=255, unique=True)
    to = models.CharField(max_length=32)
    template = models.CharField(max_length=100)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sms_logs",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    provider_message_id = models.CharField(max_length=64, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"{self.template} to {self.to}: {self.status}"
