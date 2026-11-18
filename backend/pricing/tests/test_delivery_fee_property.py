"""Property: the delivery fee never decreases as distance increases.

Plain pytest instead of Hypothesis, because adding Hypothesis needs the
tech lead's approval. Each rule set is checked over many distances.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

# 0 km to 60 km in 37 m steps, plus some awkward values.
DISTANCES = sorted(
    {Decimal(step * 37) / Decimal(1000) for step in range(0, 1622)}
    | {Decimal("0.001"), Decimal("1.999"), Decimal("2"), Decimal("2.001")}
)

RULE_SETS = [
    (39, 10),
    (0, 0),
    (0, 1),
    (49, Decimal("7.5")),
    (Decimal("39.99"), Decimal("0.01")),
    (100, 25),
]


@pytest.mark.parametrize(("base_fee", "per_km"), RULE_SETS)
def test_fee_never_decreases_as_distance_increases(base_fee, per_km) -> None:
    from pricing.delivery_fee import delivery_fee_for_km

    fees = [
        delivery_fee_for_km(km, base_fee=base_fee, per_km=per_km)
        for km in DISTANCES
    ]

    assert all(near <= far for near, far in zip(fees, fees[1:], strict=False))
    assert fees[0] == Decimal(str(base_fee)).quantize(Decimal("0.01"))


def test_sample_order_delivery_fee() -> None:
    """The workflow's sample order: delivery 59 with the default settings.

    Sample: items 535, delivery 59, service fee 5, bill 1000 -> total 599,
    change 401. With delivery_base_fee 39 and delivery_per_km 10, a 2 km
    trip gives the sample's 59.
    """
    from pricing.delivery_fee import delivery_fee_for_km

    delivery = delivery_fee_for_km(Decimal("2"), base_fee=39, per_km=10)

    assert delivery == Decimal("59.00")
    assert Decimal("535") + delivery + Decimal("5") == Decimal("599")
