"""The handoff after an order's status changes (S2-15.1).

This only queues orders.tasks.order_status_changed. It deliberately writes no
SMS text and looks up no phone number: users have no phone field yet, and the
wording belongs to other cards.

- S3-16 (Send the customer SMS messages): "accepted" and "rejected, reason".
- S2-15.2 (Axel) and S2-07.2 (Christian): the shop's alert and its wording.

Those owners fill in the task, using sms.tasks.send_sms with an event_key of
"order:<id>:<status>" so a repeated event sends one text.
"""

from __future__ import annotations


def order_status_changed(order_id: int, status: str) -> None:
    from .tasks import order_status_changed as task

    task.delay(order_id, status)
