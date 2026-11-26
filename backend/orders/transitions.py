"""Order status changes (S2-15.1). Every status change goes through transition().

An order in New can be moved by the merchant's Accept, the merchant's Reject
(maybe from a second device) and, from S2-16.1, the accept timer. They can
arrive at the same moment, so transition() locks the order row first and only
then reads its status: exactly one of them wins and the others are told why.

    New -> Accepted      (merchant, before the accept deadline)
    New -> Rejected      (merchant, before the accept deadline, with a reason)

S2-16.1 adds New -> Cancelled to ALLOWED and calls accept_deadline() from its
timer, so the timer and this API can never disagree about "too late".
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from audit.log import record
from settings_store.cache import get_setting

from . import notify
from .models import Order, OrderStatusHistory

ALLOWED: dict[str, frozenset[str]] = {
    Order.Status.NEW: frozenset({Order.Status.ACCEPTED, Order.Status.REJECTED}),
}

# Statuses that are a shop's decision on a New order.
DECISIONS = frozenset({Order.Status.ACCEPTED, Order.Status.REJECTED})


class TransitionError(Exception):
    """A status change that was refused. code is one of:

    not_allowed      the order is not in a status that can move there
    deadline_passed  the accept window (accept_minutes) has closed
    reason_required  a rejection without a reason
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def accept_deadline(order: Order) -> datetime:
    """When the shop's time to decide ends.

    accept_minutes is read every time, so an admin change applies to the next
    check, as the card asks.
    """
    return order.created_at + timedelta(minutes=int(get_setting("accept_minutes")))


def latest_reason(order: Order) -> str | None:
    """The reason on the order's Rejected history row, or None."""
    if order.status != Order.Status.REJECTED:
        return None
    return (
        order.status_history.filter(status=Order.Status.REJECTED)
        .values_list("reason", flat=True)
        .last()
    )


def transition(
    *,
    order_id: int,
    to: str,
    by,
    reason: str = "",
    now: datetime | None = None,
) -> tuple[Order, bool]:
    """Move the order to `to`. Returns (order, changed).

    changed is False when the order already made exactly this decision, so a
    repeated tap is answered the same way and nothing is written twice.
    Raises TransitionError for anything refused, and Order.DoesNotExist.
    """
    reason = reason.strip()
    if to == Order.Status.REJECTED and not reason:
        raise TransitionError("reason_required", "A rejection needs a reason.")

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        before = order.status

        if (
            before == to
            and to in DECISIONS
            and (to != Order.Status.REJECTED or latest_reason(order) == reason)
        ):
            return order, False
        if to not in ALLOWED.get(before, frozenset()):
            raise TransitionError(
                "not_allowed", f"An order that is {before} cannot become {to}."
            )
        if to in DECISIONS and (now or timezone.now()) > accept_deadline(order):
            raise TransitionError(
                "deadline_passed", "The time to accept this order has passed."
            )

        order.status = to
        order.save(update_fields=["status"])
        OrderStatusHistory.objects.create(
            order=order, status=to, changed_by=by, reason=reason
        )
        after = {"status": to}
        if reason:
            after["reason"] = reason
        record(
            who=by,
            what=f"order.{to}",
            target=order,
            before={"status": before},
            after=after,
        )
        # robust: the decision is already committed, so a broker outage is
        # logged instead of turning it into a failed request.
        transaction.on_commit(
            lambda: notify.order_status_changed(order.pk, to), robust=True
        )

    return order, True
