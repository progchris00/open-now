from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def configure_django() -> None:
    sys.path.insert(0, str(BACKEND_ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_settings"

    import django

    django.setup()


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    configure_django()

    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)


@pytest.fixture
def discount_percent():
    """Set senior_pwd_discount_percent inside a rolled-back transaction."""
    from django.db import transaction

    from settings_store.cache import invalidate_settings_cache
    from settings_store.models import Setting

    def set_percent(value: object) -> None:
        Setting.objects.filter(key="senior_pwd_discount_percent").update(value=value)
        invalidate_settings_cache()

    invalidate_settings_cache()
    with transaction.atomic():
        set_percent(20)
        yield set_percent
        transaction.set_rollback(True)
    invalidate_settings_cache()


def _sample_cart():
    """The sample cart's 535 of items: 300 eligible, 235 not eligible."""
    from pricing.discount import CartLine

    return [
        CartLine(unit_price=Decimal("150"), quantity=2, discount_eligible=True),
        CartLine(unit_price=Decimal("235"), quantity=1, discount_eligible=False),
    ]


def test_discount_only_on_eligible_items(discount_percent) -> None:
    from pricing.discount import eligible_subtotal, senior_pwd_discount

    cart = _sample_cart()

    assert eligible_subtotal(cart) == Decimal("300.00")
    # 20% of the 300 eligible, not of the full 535
    assert senior_pwd_discount(cart, senior_pwd=True) == Decimal("60.00")


def test_no_discount_without_the_tick(discount_percent) -> None:
    from pricing.discount import senior_pwd_discount

    assert senior_pwd_discount(_sample_cart(), senior_pwd=False) == Decimal("0.00")


def test_no_eligible_items_means_no_discount(discount_percent) -> None:
    from pricing.discount import CartLine, senior_pwd_discount

    cart = [CartLine(unit_price=Decimal("535"), quantity=1, discount_eligible=False)]

    assert senior_pwd_discount(cart, senior_pwd=True) == Decimal("0.00")


def test_discount_from_settings(discount_percent) -> None:
    from pricing.discount import senior_pwd_discount

    discount_percent(20)
    at_twenty = senior_pwd_discount(_sample_cart(), senior_pwd=True)
    discount_percent(12.5)
    at_twelve_and_a_half = senior_pwd_discount(_sample_cart(), senior_pwd=True)
    discount_percent(0)
    at_zero = senior_pwd_discount(_sample_cart(), senior_pwd=True)

    assert at_twenty == Decimal("60.00")
    assert at_twelve_and_a_half == Decimal("37.50")
    assert at_zero == Decimal("0.00")


def test_discount_is_rounded_to_the_centavo() -> None:
    from pricing.discount import CartLine, senior_pwd_discount

    cart = [CartLine(unit_price=Decimal("33.33"), quantity=1, discount_eligible=True)]

    # 20% of 33.33 = 6.666 -> 6.67
    assert senior_pwd_discount(cart, senior_pwd=True, percent=20) == Decimal("6.67")


def test_bad_lines_and_percents_are_rejected() -> None:
    from pricing.discount import CartLine, eligible_subtotal, senior_pwd_discount

    with pytest.raises(ValueError):
        eligible_subtotal(
            [CartLine(unit_price=Decimal("-1"), quantity=1, discount_eligible=True)]
        )
    with pytest.raises(ValueError):
        eligible_subtotal(
            [CartLine(unit_price=Decimal("10"), quantity=-1, discount_eligible=True)]
        )
    with pytest.raises(ValueError):
        senior_pwd_discount(_sample_cart(), senior_pwd=True, percent=101)
    with pytest.raises(ValueError):
        senior_pwd_discount(_sample_cart(), senior_pwd=True, percent=-1)
