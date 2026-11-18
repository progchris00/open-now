"""Property: total == items + delivery + fee - discount for non-negative amounts.

Plain pytest instead of Hypothesis, because adding Hypothesis needs the
tech lead's approval. The amounts below cover zeros, centavos and large
values in every combination.
"""

from __future__ import annotations

import itertools
import sys
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

AMOUNTS = [
    Decimal("0"),
    Decimal("0.01"),
    Decimal("5"),
    Decimal("39.99"),
    Decimal("59"),
    Decimal("535"),
    Decimal("1000"),
    Decimal("99999.99"),
]
DISCOUNTS = [Decimal("0"), Decimal("0.01"), Decimal("20"), Decimal("107")]


@pytest.mark.parametrize(
    ("items", "delivery", "fee"),
    list(itertools.product(AMOUNTS, repeat=3)),
)
def test_total_is_items_plus_delivery_plus_fee_minus_discount(
    items, delivery, fee
) -> None:
    from orders.cash import order_total

    for discount in DISCOUNTS:
        if discount > items + delivery + fee:
            with pytest.raises(ValueError):
                order_total(items, delivery, fee, discount=discount)
            continue

        total = order_total(items, delivery, fee, discount=discount)

        assert total == items + delivery + fee - discount
        assert total >= 0
        assert isinstance(total, Decimal)


def test_sample_order() -> None:
    """The workflow's sample order.

    Items 535, delivery 59, service fee 5, bill 1000: total 599, change 401.
    (The "to shop 540" and "rider cash 1000 to 1059" parts are the order's
    cash settlement, which belongs to S2-12.)
    """
    from orders.cash import change_due, order_total

    total = order_total(Decimal("535"), Decimal("59"), Decimal("5"))

    assert total == Decimal("599.00")
    assert change_due(bill=Decimal("1000"), total=total) == Decimal("401.00")


def test_bill_must_cover_the_total() -> None:
    from orders.cash import change_due

    assert change_due(bill=Decimal("599"), total=Decimal("599")) == Decimal("0.00")
    with pytest.raises(ValueError):
        change_due(bill=Decimal("500"), total=Decimal("599"))


def test_negative_amounts_are_rejected() -> None:
    from orders.cash import order_total

    with pytest.raises(ValueError):
        order_total(Decimal("-1"), Decimal("0"), Decimal("0"))
    with pytest.raises(ValueError):
        order_total(Decimal("1"), Decimal("0"), Decimal("0"), discount=Decimal("-1"))


def test_amounts_are_rounded_to_the_centavo() -> None:
    from orders.cash import change_due, order_total

    assert order_total(10.005, 0, 0) == Decimal("10.01")
    assert change_due(bill=1000, total=599) == Decimal("401.00")
