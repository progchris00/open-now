"""Shared fixtures for the order placement tests (S2-12.1).

The tests run against the development database, like the audit and settings
tests: every test runs inside a transaction that is rolled back, and the
settings cache is cleared before and after so no test value leaks out.
"""

from __future__ import annotations

import base64
import os
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# The settings the sample order is worked out with:
# 535 items + (39 + 10/km x 2 km) delivery + 5 fee = 599.
SAMPLE_SETTINGS = {
    "payment_method": "cod",
    "service_fee_per_order": 5,
    "delivery_base_fee": 39,
    "delivery_per_km": 10,
    "accept_minutes": 5,
}
SAMPLE_DISTANCE_KM = "2"
PASSWORD = "test-password"


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
def rollback(migrated_database):
    """Run the test in a transaction that is rolled back afterwards."""
    from django.db import transaction

    from settings_store.cache import invalidate_settings_cache

    invalidate_settings_cache()
    with transaction.atomic():
        yield
        transaction.set_rollback(True)
    invalidate_settings_cache()


@pytest.fixture
def new_orders(rollback):
    """How many orders this test created.

    The development database can already hold real orders, so tests count
    from where they started instead of assuming the table is empty.
    """
    from orders.models import Order

    start = Order.objects.count()
    return lambda: Order.objects.count() - start


@pytest.fixture
def set_settings(rollback):
    """Change admin settings for this test only. Starts from SAMPLE_SETTINGS."""
    from settings_store.cache import invalidate_settings_cache
    from settings_store.models import Setting

    def apply(**values: object) -> None:
        for key, value in values.items():
            updated = Setting.objects.filter(key=key).update(value=value)
            assert updated == 1, f"Setting {key!r} is not seeded"
        invalidate_settings_cache()

    apply(**SAMPLE_SETTINGS)
    return apply


def make_user(*, customer: bool):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    from orders.permissions import CUSTOMER_GROUP

    user = get_user_model().objects.create_user(
        username=f"order-test-{uuid4().hex}",
        password=PASSWORD,
    )
    if customer:
        group, _ = Group.objects.get_or_create(name=CUSTOMER_GROUP)
        user.groups.add(group)
    return user


def basic_auth(user) -> str:
    token = base64.b64encode(f"{user.username}:{PASSWORD}".encode()).decode()
    return f"Basic {token}"


@pytest.fixture
def customer(set_settings):
    return make_user(customer=True)


@pytest.fixture
def customer_client(customer):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=customer)
    return client


@pytest.fixture
def menu(set_settings):
    """Two products from one shop: 250 x 1 + 95 x 3 = 535 of items."""
    from orders.models import Product

    shop_id = 1
    return {
        "adobo": Product.objects.create(
            shop_id=shop_id, name="Chicken adobo", price=Decimal("250.00")
        ),
        "rice": Product.objects.create(
            shop_id=shop_id, name="Garlic rice", price=Decimal("95.00")
        ),
    }


@pytest.fixture
def sample_request(menu):
    """The workflow's sample order: 535 items, 59 delivery, 5 fee, 1000 bill."""
    return {
        "items": [
            {"product_id": menu["adobo"].pk, "quantity": 1},
            {"product_id": menu["rice"].pk, "quantity": 3},
        ],
        "distance_km": SAMPLE_DISTANCE_KM,
        "bill": "1000.00",
        "payment_method": "cod",
    }


@pytest.fixture
def place(customer_client):
    """POST /api/orders with a fresh Idempotency-Key unless one is given."""

    def post(body, *, key: str | None = None, client=None):
        return (client or customer_client).post(
            "/api/orders",
            body,
            format="json",
            headers={"Idempotency-Key": key or uuid4().hex},
        )

    return post
