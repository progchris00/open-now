from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_LIMITS = {
    "limit_new_customer": 1000,
    "open_orders_new": 1,
    "limit_regular": 3000,
    "open_orders_regular": 3,
}


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
def limits():
    """Set the four limit settings inside a transaction that is rolled back."""
    from django.db import transaction

    from settings_store.cache import invalidate_settings_cache
    from settings_store.models import Setting

    def set_limits(**values: object) -> None:
        for key, value in values.items():
            Setting.objects.filter(key=key).update(value=value)
        invalidate_settings_cache()

    invalidate_settings_cache()
    with transaction.atomic():
        set_limits(**DEFAULT_LIMITS)
        yield set_limits
        transaction.set_rollback(True)
    invalidate_settings_cache()


def test_new_customer_limit(limits) -> None:
    from orders.limits import Decision, Level, check_order_limits

    at_limit = check_order_limits(
        order_total=Decimal("1000"), completed_orders=0, open_orders=0
    )
    over_limit = check_order_limits(
        order_total=Decimal("1000.01"), completed_orders=0, open_orders=0
    )

    assert at_limit.level is Level.NEW
    assert at_limit.decision is Decision.ACCEPT
    assert over_limit.level is Level.NEW
    assert over_limit.decision is Decision.HOLD_FOR_SHOP_CALL


def test_over_limit_needs_shop_call(limits) -> None:
    from orders.limits import Decision, check_order_limits

    result = check_order_limits(
        order_total=Decimal("1200"), completed_orders=0, open_orders=0
    )

    assert result.decision is Decision.HOLD_FOR_SHOP_CALL
    assert result.needs_shop_call is True
    assert result.limit == Decimal("1000")
    assert "call" in result.message.lower()


def test_regular_after_one_completed(limits) -> None:
    from orders.limits import Decision, Level, check_order_limits

    # 1,200 is over the new-customer limit but under the regular one.
    result = check_order_limits(
        order_total=Decimal("1200"), completed_orders=1, open_orders=2
    )
    over_regular = check_order_limits(
        order_total=Decimal("3000.01"), completed_orders=5, open_orders=0
    )

    assert result.level is Level.REGULAR
    assert result.decision is Decision.ACCEPT
    assert result.needs_shop_call is False
    assert over_regular.decision is Decision.HOLD_FOR_SHOP_CALL
    assert over_regular.limit == Decimal("3000")


def test_open_order_count(limits) -> None:
    from orders.limits import Decision, check_order_limits

    new_with_one_open = check_order_limits(
        order_total=Decimal("100"), completed_orders=0, open_orders=1
    )
    regular_with_two_open = check_order_limits(
        order_total=Decimal("100"), completed_orders=1, open_orders=2
    )
    regular_with_three_open = check_order_limits(
        order_total=Decimal("100"), completed_orders=1, open_orders=3
    )

    assert new_with_one_open.decision is Decision.REFUSE_TOO_MANY_OPEN_ORDERS
    assert regular_with_two_open.decision is Decision.ACCEPT
    assert regular_with_three_open.decision is Decision.REFUSE_TOO_MANY_OPEN_ORDERS
    assert "open order" in regular_with_three_open.message.lower()


def test_too_many_open_orders_is_refused_even_when_over_the_limit(limits) -> None:
    from orders.limits import Decision, check_order_limits

    result = check_order_limits(
        order_total=Decimal("5000"), completed_orders=0, open_orders=1
    )

    assert result.decision is Decision.REFUSE_TOO_MANY_OPEN_ORDERS


def test_limit_values_come_from_settings(limits) -> None:
    from orders.limits import Decision, check_order_limits

    limits(
        limit_new_customer=500,
        open_orders_new=2,
        limit_regular=800,
        open_orders_regular=1,
    )

    assert (
        check_order_limits(
            order_total=Decimal("600"), completed_orders=0, open_orders=1
        ).decision
        is Decision.HOLD_FOR_SHOP_CALL
    )
    assert (
        check_order_limits(
            order_total=Decimal("700"), completed_orders=1, open_orders=0
        ).decision
        is Decision.ACCEPT
    )
    assert (
        check_order_limits(
            order_total=Decimal("100"), completed_orders=1, open_orders=1
        ).decision
        is Decision.REFUSE_TOO_MANY_OPEN_ORDERS
    )


def test_customer_level_from_completed_orders() -> None:
    from orders.limits import Level, customer_level

    assert customer_level(0) is Level.NEW
    assert customer_level(1) is Level.REGULAR
    assert customer_level(12) is Level.REGULAR

    with pytest.raises(ValueError):
        customer_level(-1)


def test_negative_counts_or_total_are_rejected(limits) -> None:
    from orders.limits import check_order_limits

    with pytest.raises(ValueError):
        check_order_limits(
            order_total=Decimal("-1"), completed_orders=0, open_orders=0
        )
    with pytest.raises(ValueError):
        check_order_limits(
            order_total=Decimal("10"), completed_orders=0, open_orders=-1
        )
