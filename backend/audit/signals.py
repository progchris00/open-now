from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import AuditLog, CashRecord, Order


@receiver(pre_save, sender=Order)
def capture_order_status(sender, instance, using, update_fields, raw, **kwargs):
    if raw:
        return

    if instance.status not in Order.Status.values:
        raise ValidationError({"status": "Invalid order status."})

    instance._audit_status_changed = False
    if instance._state.adding:
        return

    before = (
        sender.objects.using(using)
        .select_for_update()
        .values_list("status", flat=True)
        .get(pk=instance.pk)
    )
    status_is_saved = update_fields is None or "status" in update_fields
    if status_is_saved and before != instance.status:
        actor = getattr(instance, "_audit_actor", None)
        if actor is None:
            raise PermissionError("Order status changes require an actor.")
        instance._audit_status_before = before
        instance._audit_status_changed = True


@receiver(post_save, sender=Order)
def write_order_status_audit(sender, instance, using, created, raw, **kwargs):
    if raw:
        return

    if not created and getattr(instance, "_audit_status_changed", False):
        AuditLog.objects.db_manager(using).create(
            who=instance._audit_actor,
            what="order.status",
            before=instance._audit_status_before,
            after=instance.status,
        )

    for attribute in ("_audit_status_before", "_audit_status_changed"):
        if hasattr(instance, attribute):
            delattr(instance, attribute)


@receiver(post_save, sender=CashRecord)
def write_cash_record_audit(sender, instance, using, created, raw, **kwargs):
    if raw or not created:
        return

    AuditLog.objects.db_manager(using).create(
        who=instance.actor,
        what="cash.record",
        before=None,
        after=instance.label,
    )
