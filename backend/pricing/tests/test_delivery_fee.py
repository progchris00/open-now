from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Two real points in Los Banos, Laguna, about 1.6 km apart.
SHOP_POINT = (14.1650, 121.2420)
CUSTOMER_PIN = (14.1675, 121.2565)


def configure_django() -> None:
    sys.path.insert(0, str(BACKEND_ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_settings"

    import django

    django.setup()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    configure_django()

    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)


@pytest.fixture
def rollback():
    """Run the test inside a transaction that is always rolled back."""
    from django.db import transaction

    from settings_store.cache import invalidate_settings_cache

    invalidate_settings_cache()
    with transaction.atomic():
        yield
        transaction.set_rollback(True)
    invalidate_settings_cache()


def _set_setting(key: str, value: object) -> None:
    from settings_store.cache import invalidate_settings_cache
    from settings_store.models import Setting

    Setting.objects.filter(key=key).update(value=value)
    invalidate_settings_cache()


def _postgis_km(origin: tuple[float, float], destination: tuple[float, float]):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT ST_Distance("
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography) / 1000.0",
            [origin[1], origin[0], destination[1], destination[0]],
        )
        return cursor.fetchone()[0]


def test_fee_uses_postgis_distance(rollback) -> None:
    from pricing.delivery_fee import distance_km, quote_delivery_fee

    _set_setting("delivery_base_fee", 39)
    _set_setting("delivery_per_km", 10)

    km = distance_km(SHOP_POINT, CUSTOMER_PIN)

    # The distance is PostGIS's geodesic distance, to the metre.
    assert km == Decimal(str(round(_postgis_km(SHOP_POINT, CUSTOMER_PIN), 3)))
    assert Decimal("1.5") < km < Decimal("1.7")

    # fee = delivery_base_fee + delivery_per_km x km, exact to the centavo
    expected = (Decimal("39") + Decimal("10") * km).quantize(Decimal("0.01"))
    assert quote_delivery_fee(SHOP_POINT, pin=CUSTOMER_PIN) == expected


def test_fee_uses_barangay_center_without_pin(rollback) -> None:
    from pricing.delivery_fee import quote_delivery_fee
    from pricing.models import Barangay

    barangay = Barangay.objects.create(
        name="Test Barangay",
        center_lat=Decimal(str(CUSTOMER_PIN[0])),
        center_lng=Decimal(str(CUSTOMER_PIN[1])),
    )

    without_pin = quote_delivery_fee(SHOP_POINT, barangay=barangay)

    assert without_pin == quote_delivery_fee(SHOP_POINT, pin=CUSTOMER_PIN)


def test_pin_wins_over_barangay_center(rollback) -> None:
    from pricing.delivery_fee import quote_delivery_fee
    from pricing.models import Barangay

    far_barangay = Barangay.objects.create(
        name="Far Barangay",
        center_lat=Decimal("14.2000"),
        center_lng=Decimal("121.3000"),
    )

    assert quote_delivery_fee(
        SHOP_POINT, pin=CUSTOMER_PIN, barangay=far_barangay
    ) == quote_delivery_fee(SHOP_POINT, pin=CUSTOMER_PIN)


def test_fee_values_from_settings(rollback) -> None:
    from pricing.delivery_fee import quote_delivery_fee

    _set_setting("delivery_base_fee", 39)
    _set_setting("delivery_per_km", 10)
    before = quote_delivery_fee(SHOP_POINT, pin=SHOP_POINT)

    _set_setting("delivery_base_fee", 50)
    _set_setting("delivery_per_km", 12.5)
    after_zero_km = quote_delivery_fee(SHOP_POINT, pin=SHOP_POINT)
    after = quote_delivery_fee(SHOP_POINT, pin=CUSTOMER_PIN)

    assert before == Decimal("39.00")
    assert after_zero_km == Decimal("50.00")
    assert after > after_zero_km


def test_same_point_costs_only_the_base_fee(rollback) -> None:
    from pricing.delivery_fee import distance_km, quote_delivery_fee

    _set_setting("delivery_base_fee", 39)

    assert distance_km(SHOP_POINT, SHOP_POINT) == Decimal("0")
    assert quote_delivery_fee(SHOP_POINT, pin=SHOP_POINT) == Decimal("39.00")


def test_quote_needs_a_pin_or_a_barangay(rollback) -> None:
    from pricing.delivery_fee import quote_delivery_fee

    with pytest.raises(ValueError):
        quote_delivery_fee(SHOP_POINT)


def test_fee_is_a_decimal_rounded_to_the_centavo() -> None:
    from pricing.delivery_fee import delivery_fee_for_km

    fee = delivery_fee_for_km(Decimal("2.315"), base_fee=39, per_km=10)

    # 39 + 10 x 2.315 = 62.15
    assert fee == Decimal("62.15")
    assert isinstance(fee, Decimal)
    assert delivery_fee_for_km(
        Decimal("1.0005"), base_fee=39, per_km=Decimal("0.5")
    ) == Decimal("39.50")


def test_negative_distance_is_rejected() -> None:
    from pricing.delivery_fee import delivery_fee_for_km

    with pytest.raises(ValueError):
        delivery_fee_for_km(Decimal("-0.1"), base_fee=39, per_km=10)


def test_barangay_str_is_its_name(rollback) -> None:
    from pricing.models import Barangay

    barangay = Barangay.objects.create(
        name="Batong Malake",
        center_lat=Decimal("14.1650"),
        center_lng=Decimal("121.2420"),
    )

    assert str(barangay) == "Batong Malake"
