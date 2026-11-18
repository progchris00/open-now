from django.db import models

from .models import AuditLog


def record(
    *,
    who,
    what,
    target: models.Model,
    before=None,
    after=None,
) -> AuditLog:
    return AuditLog.objects.create(
        who=who,
        what=what,
        target_type=target._meta.label_lower,
        target_id=str(target.pk),
        before=before,
        after=after,
    )
