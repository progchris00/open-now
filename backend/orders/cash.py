"""Cash maths for an order (S2-14.1). Decimal pesos, rounded to the centavo.

    total  = items + delivery + fee - discount
    change = bill - total   (the bill picked must be at least the total)
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

Amount = Decimal | float | int

CENTAVO = Decimal("0.01")


def to_peso(value: Amount) -> Decimal:
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    return amount.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def order_total(
    items: Amount,
    delivery: Amount,
    fee: Amount,
    *,
    discount: Amount = 0,
) -> Decimal:
    """items + delivery + fee - discount. Every amount must be non-negative."""
    parts = [to_peso(items), to_peso(delivery), to_peso(fee), to_peso(discount)]
    if any(part < 0 for part in parts):
        raise ValueError("Amounts cannot be negative.")

    items_, delivery_, fee_, discount_ = parts
    subtotal = items_ + delivery_ + fee_
    if discount_ > subtotal:
        raise ValueError("The discount cannot be more than the order.")
    return subtotal - discount_


def change_due(*, bill: Amount, total: Amount) -> Decimal:
    """Change to give back. The bill picked must be at least the total."""
    bill_, total_ = to_peso(bill), to_peso(total)
    if bill_ < total_:
        raise ValueError("The bill picked must be at least the total.")
    return bill_ - total_
