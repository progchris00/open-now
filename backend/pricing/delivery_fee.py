"""Delivery fee from distance (ON-30 / S1-15).

    fee = delivery_base_fee + delivery_per_km x km

The distance is PostGIS's geodesic distance between the shop point and the
customer's pin, or the barangay center when there is no pin. Both numbers
are admin settings (settings_store), so nothing here is hard-coded. Fees are
Decimal pesos, rounded to the centavo.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from django.db import connection

if TYPE_CHECKING:
    from .models import Barangay

Point = tuple[float, float]
"""A (latitude, longitude) pair in decimal degrees (WGS 84)."""

CENTAVO = Decimal("0.01")

_DISTANCE_SQL = (
    "SELECT ST_Distance("
    "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, "
    "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) / 1000.0"
)


def _decimal(value: Decimal | float | int) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def distance_km(origin: Point, destination: Point) -> Decimal:
    """PostGIS geodesic distance between two points, in km to the metre."""
    with connection.cursor() as cursor:
        cursor.execute(
            _DISTANCE_SQL,
            [origin[1], origin[0], destination[1], destination[0]],
        )
        km = cursor.fetchone()[0]
    return Decimal(str(round(km, 3)))


def delivery_fee_for_km(
    km: Decimal | float | int,
    *,
    base_fee: Decimal | float | int,
    per_km: Decimal | float | int,
) -> Decimal:
    """base_fee + per_km x km, rounded to the centavo."""
    km = _decimal(km)
    if km < 0:
        raise ValueError("Distance cannot be negative.")

    fee = _decimal(base_fee) + _decimal(per_km) * km
    return fee.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def quote_delivery_fee(
    shop_point: Point,
    *,
    pin: Point | None = None,
    barangay: Barangay | None = None,
) -> Decimal:
    """Delivery fee from the shop to the pin, or to the barangay center."""
    from settings_store.cache import get_setting

    if pin is not None:
        destination = pin
    elif barangay is not None:
        destination = barangay.center
    else:
        raise ValueError("A quote needs a customer pin or a barangay.")

    return delivery_fee_for_km(
        distance_km(shop_point, destination),
        base_fee=get_setting("delivery_base_fee"),
        per_km=get_setting("delivery_per_km"),
    )
