from django.conf import settings
from django.db import models


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
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    what = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=255)
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
