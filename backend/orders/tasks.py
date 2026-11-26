from celery import shared_task

from .models import Order


@shared_task
def accept_timer_expired(order_id: int) -> str | None:
    """Fires accept_minutes after an order is placed.

    S2-16.1 cancels the order here if the shop still hasn't accepted it.
    Until then it only reports the order's status (None if it's gone).
    """
    return Order.objects.filter(pk=order_id).values_list("status", flat=True).first()


@shared_task
def order_status_changed(order_id: int, status: str) -> str | None:
    """Queued after an order's status change commits (see orders.notify).

    S3-16 sends the customer's SMS from here. Until then it only reports the
    order's current status (None if it's gone).
    """
    return Order.objects.filter(pk=order_id).values_list("status", flat=True).first()
