"""Property: the discount never exceeds the eligible item subtotal (S2-13.1)."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from hypothesis import example, given
from hypothesis import strategies as st

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from pricing.discount import (  # noqa: E402
    CartLine,
    eligible_subtotal,
    senior_pwd_discount,
)

LINES = st.lists(
    st.builds(
        CartLine,
        unit_price=st.decimals(min_value=0, max_value=10_000, places=2),
        quantity=st.integers(min_value=0, max_value=50),
        discount_eligible=st.booleans(),
    ),
    max_size=12,
)
PERCENT = st.decimals(min_value=0, max_value=100, places=4)


@given(lines=LINES, percent=PERCENT)
@example(  # the sample order: 535 of items, all eligible, at 20%
    lines=[CartLine(unit_price=Decimal("535"), quantity=1, discount_eligible=True)],
    percent=Decimal("20"),
)
def test_discount_never_exceeds_the_eligible_subtotal(lines, percent) -> None:
    discount = senior_pwd_discount(lines, senior_pwd=True, percent=percent)

    assert Decimal("0") <= discount <= eligible_subtotal(lines)
    assert senior_pwd_discount(lines, senior_pwd=False, percent=percent) == 0


def test_sample_order() -> None:
    """The workflow's sample order: items 535, delivery 59, fee 5, bill 1000.

    Without the tick there is no discount, so the total stays 599 and the
    change 401. With the tick and all 535 eligible at 20%, 107 comes off.
    """
    cart = [CartLine(unit_price=Decimal("535"), quantity=1, discount_eligible=True)]

    no_tick = senior_pwd_discount(cart, senior_pwd=False, percent=20)
    ticked = senior_pwd_discount(cart, senior_pwd=True, percent=20)

    assert no_tick == Decimal("0.00")
    assert Decimal("535") + Decimal("59") + Decimal("5") - no_tick == Decimal("599")
    assert Decimal("1000") - Decimal("599") == Decimal("401")
    assert ticked == Decimal("107.00")
