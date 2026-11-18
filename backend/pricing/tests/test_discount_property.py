"""Property: the discount never exceeds the eligible item subtotal.

Plain pytest instead of Hypothesis, because adding Hypothesis needs the
tech lead's approval. Every combination of the values below is checked.
"""

from __future__ import annotations

import itertools
import sys
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

PRICES = [Decimal("0"), Decimal("0.01"), Decimal("33.33"), Decimal("150"),
          Decimal("535"), Decimal("9999.99")]
QUANTITIES = [0, 1, 3]
PERCENTS = [0, Decimal("0.5"), Decimal("12.5"), 20, Decimal("33.3333"), 99, 100]


@pytest.mark.parametrize(
    ("eligible_price", "other_price", "quantity", "percent"),
    list(itertools.product(PRICES, PRICES, QUANTITIES, PERCENTS)),
)
def test_discount_never_exceeds_the_eligible_subtotal(
    eligible_price, other_price, quantity, percent
) -> None:
    from pricing.discount import CartLine, eligible_subtotal, senior_pwd_discount

    cart = [
        CartLine(unit_price=eligible_price, quantity=quantity, discount_eligible=True),
        CartLine(unit_price=other_price, quantity=1, discount_eligible=False),
    ]

    discount = senior_pwd_discount(cart, senior_pwd=True, percent=percent)

    assert Decimal("0") <= discount <= eligible_subtotal(cart)
    assert senior_pwd_discount(cart, senior_pwd=False, percent=percent) == 0


def test_sample_order() -> None:
    """The workflow's sample order: items 535, delivery 59, fee 5, bill 1000.

    Without the tick there is no discount, so the total stays 599 and the
    change 401. With the tick and all 535 eligible at 20%, 107 comes off.
    """
    from pricing.discount import CartLine, senior_pwd_discount

    cart = [CartLine(unit_price=Decimal("535"), quantity=1, discount_eligible=True)]

    no_tick = senior_pwd_discount(cart, senior_pwd=False, percent=20)
    ticked = senior_pwd_discount(cart, senior_pwd=True, percent=20)

    assert no_tick == Decimal("0.00")
    assert Decimal("535") + Decimal("59") + Decimal("5") - no_tick == Decimal("599")
    assert Decimal("1000") - Decimal("599") == Decimal("401")
    assert ticked == Decimal("107.00")
