"""Senior and PWD discount (ON-43 / S2-13.1).

When the customer ticks Senior or PWD, senior_pwd_discount_percent (an admin
setting) comes off the subtotal of the discount-eligible items only. Delivery
and the service fee are never discounted. Decimal pesos, rounded to the
centavo, so the discount can never be more than the eligible subtotal.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

Amount = Decimal | float | int

CENTAVO = Decimal("0.01")
HUNDRED = Decimal("100")


def _decimal(value: Amount) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class CartLine:
    unit_price: Amount
    quantity: int
    discount_eligible: bool


def eligible_subtotal(lines: Iterable[CartLine]) -> Decimal:
    """Sum of price x quantity for the discount-eligible lines."""
    subtotal = Decimal("0")
    for line in lines:
        price = _decimal(line.unit_price)
        if price < 0 or line.quantity < 0:
            raise ValueError("Prices and quantities cannot be negative.")
        if line.discount_eligible:
            subtotal += price * line.quantity
    return subtotal.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def senior_pwd_discount(
    lines: Iterable[CartLine],
    *,
    senior_pwd: bool,
    percent: Amount | None = None,
) -> Decimal:
    """Discount in pesos for a Senior or PWD customer, else 0.

    ``percent`` defaults to the senior_pwd_discount_percent admin setting.
    """
    lines = list(lines)
    subtotal = eligible_subtotal(lines)
    if not senior_pwd:
        return Decimal("0.00")

    if percent is None:
        from settings_store.cache import get_setting

        percent = get_setting("senior_pwd_discount_percent")
    rate = _decimal(percent)
    if not Decimal("0") <= rate <= HUNDRED:
        raise ValueError("The discount percent must be between 0 and 100.")

    return (subtotal * rate / HUNDRED).quantize(CENTAVO, rounding=ROUND_HALF_UP)
