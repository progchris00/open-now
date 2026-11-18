"""Order limits by customer level (S2-14.1).

A customer is NEW until they complete an order, then REGULAR. Each level has
a peso limit and a maximum number of open orders, read from admin settings:

    NEW      limit_new_customer, open_orders_new
    REGULAR  limit_regular,      open_orders_regular

Too many open orders: the order is refused with a clear message.
Over the peso limit: the order is held and the shop must call before
accepting it. Otherwise it is accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from .cash import Amount, to_peso


class Level(StrEnum):
    NEW = "new"
    REGULAR = "regular"


class Decision(StrEnum):
    ACCEPT = "accept"
    HOLD_FOR_SHOP_CALL = "hold_for_shop_call"
    REFUSE_TOO_MANY_OPEN_ORDERS = "refuse_too_many_open_orders"


_SETTING_KEYS = {
    Level.NEW: ("limit_new_customer", "open_orders_new"),
    Level.REGULAR: ("limit_regular", "open_orders_regular"),
}


@dataclass(frozen=True)
class LimitCheck:
    decision: Decision
    level: Level
    limit: Decimal
    max_open_orders: int
    message: str

    @property
    def needs_shop_call(self) -> bool:
        return self.decision is Decision.HOLD_FOR_SHOP_CALL


def customer_level(completed_orders: int) -> Level:
    """NEW until the customer has completed one order, then REGULAR."""
    if completed_orders < 0:
        raise ValueError("Completed orders cannot be negative.")
    return Level.NEW if completed_orders == 0 else Level.REGULAR


def check_order_limits(
    *,
    order_total: Amount,
    completed_orders: int,
    open_orders: int,
) -> LimitCheck:
    """Decide whether a new order is accepted, held for a call, or refused.

    ``open_orders`` is how many orders the customer already has open, not
    counting the one being placed.
    """
    from settings_store.cache import get_setting

    total = to_peso(order_total)
    if total < 0:
        raise ValueError("The order total cannot be negative.")
    if open_orders < 0:
        raise ValueError("Open orders cannot be negative.")

    level = customer_level(completed_orders)
    limit_key, open_key = _SETTING_KEYS[level]
    limit = to_peso(get_setting(limit_key))
    max_open = int(get_setting(open_key))

    if open_orders >= max_open:
        decision = Decision.REFUSE_TOO_MANY_OPEN_ORDERS
        noun = "order" if max_open == 1 else "orders"
        message = (
            f"You can have up to {max_open} open {noun} at a time. "
            "Please wait until an open order is delivered or cancelled."
        )
    elif total > limit:
        decision = Decision.HOLD_FOR_SHOP_CALL
        message = (
            f"Orders over ₱{limit:,.2f} need a quick call from the shop "
            "before they are accepted."
        )
    else:
        decision = Decision.ACCEPT
        message = "Order accepted."

    return LimitCheck(
        decision=decision,
        level=level,
        limit=limit,
        max_open_orders=max_open,
        message=message,
    )
