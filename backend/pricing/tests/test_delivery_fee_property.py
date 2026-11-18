"""Property: the delivery fee never decreases as distance increases (S1-15)."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from hypothesis import example, given
from hypothesis import strategies as st

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from pricing.delivery_fee import delivery_fee_for_km  # noqa: E402

KM = st.decimals(min_value=0, max_value=500, places=3)
PESOS = st.decimals(min_value=0, max_value=10_000, places=2)


@given(near=KM, extra=KM, base_fee=PESOS, per_km=PESOS)
@example(  # the sample order: a 2 km trip at 39 + 10/km
    near=Decimal("2"), extra=Decimal("0"), base_fee=Decimal("39"), per_km=Decimal("10")
)
def test_fee_never_decreases_as_distance_increases(
    near, extra, base_fee, per_km
) -> None:
    far = near + extra

    near_fee = delivery_fee_for_km(near, base_fee=base_fee, per_km=per_km)
    far_fee = delivery_fee_for_km(far, base_fee=base_fee, per_km=per_km)

    assert near_fee <= far_fee
    assert near_fee >= base_fee


def test_sample_order_delivery_fee() -> None:
    """The workflow's sample order: delivery 59 with the default settings.

    Sample: items 535, delivery 59, service fee 5, bill 1000 -> total 599,
    change 401. With delivery_base_fee 39 and delivery_per_km 10, a 2 km
    trip gives the sample's 59.
    """
    delivery = delivery_fee_for_km(Decimal("2"), base_fee=39, per_km=10)

    assert delivery == Decimal("59.00")
    assert Decimal("535") + delivery + Decimal("5") == Decimal("599")
