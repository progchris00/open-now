"""Properties of the order cash maths (S2-14.1).

total  == items + delivery + fee - discount for any non-negative amounts
change == bill - total, and the bill must always cover the total
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from orders.cash import change_due, order_total  # noqa: E402

PESOS = st.decimals(min_value=0, max_value=100_000, places=2)


@given(items=PESOS, delivery=PESOS, fee=PESOS, discount=PESOS)
@example(  # the sample order: 535 + 59 + 5 = 599
    items=Decimal("535"),
    delivery=Decimal("59"),
    fee=Decimal("5"),
    discount=Decimal("0"),
)
def test_total_is_items_plus_delivery_plus_fee_minus_discount(
    items, delivery, fee, discount
) -> None:
    if discount > items + delivery + fee:
        with pytest.raises(ValueError):
            order_total(items, delivery, fee, discount=discount)
        return

    total = order_total(items, delivery, fee, discount=discount)

    assert total == items + delivery + fee - discount
    assert total >= 0
    assert isinstance(total, Decimal)


@given(total=PESOS, extra=PESOS)
@example(total=Decimal("599"), extra=Decimal("401"))  # bill 1000 -> change 401
def test_change_is_bill_minus_total_and_bill_must_cover_it(total, extra) -> None:
    bill = total + extra

    assert change_due(bill=bill, total=total) == extra
    if extra > 0:
        with pytest.raises(ValueError):
            change_due(bill=total - extra, total=total)


def test_sample_order() -> None:
    """The workflow's sample order.

    Items 535, delivery 59, service fee 5, bill 1000: total 599, change 401.
    (The "to shop 540" and "rider cash 1000 to 1059" parts are the order's
    cash settlement, which belongs to S2-12.)
    """
    total = order_total(Decimal("535"), Decimal("59"), Decimal("5"))

    assert total == Decimal("599.00")
    assert change_due(bill=Decimal("1000"), total=total) == Decimal("401.00")


def test_bill_must_cover_the_total() -> None:
    assert change_due(bill=Decimal("599"), total=Decimal("599")) == Decimal("0.00")
    with pytest.raises(ValueError):
        change_due(bill=Decimal("500"), total=Decimal("599"))


def test_negative_amounts_are_rejected() -> None:
    with pytest.raises(ValueError):
        order_total(Decimal("-1"), Decimal("0"), Decimal("0"))
    with pytest.raises(ValueError):
        order_total(Decimal("1"), Decimal("0"), Decimal("0"), discount=Decimal("-1"))


def test_amounts_are_rounded_to_the_centavo() -> None:
    assert order_total(10.005, 0, 0) == Decimal("10.01")
    assert change_due(bill=1000, total=599) == Decimal("401.00")
