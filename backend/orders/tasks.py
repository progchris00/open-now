from celery import shared_task

from .models import Order


@shared_task
def accept_timer_expired(order_id: int) -> str | None:
    """Fires accept_minutes after an order is placed.

    S2-16.1 cancels the order here if the shop still hasn't accepted it.
    Until then it only reports the order's status (None if it's gone).
    """
    return Order.objects.filter(pk=order_id).values_list("status", flat=True).first()
