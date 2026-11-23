"""S2-09 acceptance tests for the append-only cash ledger."""

from __future__ import annotations

import importlib.util
import os
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def configure_django() -> None:
    sys.path.insert(0, str(BACKEND_ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.test_settings"

    import django

    django.setup()


def require_cash_module(module: str) -> None:
    assert importlib.util.find_spec(module) is not None, (
        f"The required {module} module has not been implemented yet"
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    configure_django()

    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)


@pytest.fixture(autouse=True)
def rollback(migrated_database):
    from django.db import transaction

    with transaction.atomic():
        yield
        transaction.set_rollback(True)


@pytest.fixture
def admin_and_clients(rollback):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    user_model = get_user_model()
    admin = user_model.objects.create_superuser(
        username=f"cash-admin-{uuid4().hex}",
        password="test-password",
    )
    regular = user_model.objects.create_user(
        username=f"cash-user-{uuid4().hex}",
        password="test-password",
    )
    admin_client = APIClient()
    admin_client.force_authenticate(user=admin)
    regular_client = APIClient()
    regular_client.force_authenticate(user=regular)
    return admin, admin_client, regular_client


@pytest.fixture
def order(admin_and_clients):
    from orders.models import Order

    admin, _, _ = admin_and_clients
    return Order.objects.create(
        customer=admin,
        shop_id=7,
        items_total=Decimal("535.00"),
        delivery_fee=Decimal("59.00"),
        service_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("599.00"),
        bill=Decimal("1000.00"),
        change=Decimal("401.00"),
        idempotency_key=uuid4().hex,
        request_fingerprint=uuid4().hex,
    )


def add_cash(*, order, actor, type, amount, from_party, to_party, reason=None):
    require_cash_module("cash.services")
    from cash.services import record_cash

    return record_cash(
        order=order,
        created_by=actor,
        type=type,
        amount=Decimal(amount),
        from_party=from_party,
        to_party=to_party,
        reason=reason,
    )


def test_records_immutable(order, admin_and_clients) -> None:
    require_cash_module("cash.models")
    from cash.models import CashRecord

    admin, _, _ = admin_and_clients
    record = add_cash(
        order=order,
        actor=admin,
        type="customer_payment",
        amount="1000.00",
        from_party="customer",
        to_party="rider",
    )

    with pytest.raises(PermissionError, match="read-only"):
        record.amount = Decimal("1.00")
        record.save()
    with pytest.raises(PermissionError, match="read-only"):
        record.delete()
    with pytest.raises(PermissionError, match="read-only"):
        CashRecord.objects.filter(pk=record.pk).update(amount=Decimal("1.00"))
    with pytest.raises(PermissionError, match="read-only"):
        CashRecord.objects.filter(pk=record.pk).delete()

    record.refresh_from_db()
    assert record.amount == Decimal("1000.00")


def test_correction_adds_line(order, admin_and_clients) -> None:
    require_cash_module("cash.models")
    from cash.models import CashRecord

    from audit.models import AuditLog

    admin, admin_client, regular_client = admin_and_clients
    original = add_cash(
        order=order,
        actor=admin,
        type="shop_payout",
        amount="550.00",
        from_party="rider",
        to_party="shop",
    )
    payload = {
        "order": order.pk,
        "amount": "10.00",
        "from": "shop",
        "to": "rider",
        "reason": "Shop payout was entered ten pesos too high.",
    }

    assert regular_client.post(
        "/api/admin/cash/corrections", payload, format="json"
    ).status_code == 403
    response = admin_client.post(
        "/api/admin/cash/corrections", payload, format="json"
    )

    assert response.status_code == 201
    original.refresh_from_db()
    assert original.amount == Decimal("550.00")
    correction = CashRecord.objects.get(pk=response.data["id"])
    assert CashRecord.objects.filter(order=order).count() == 2
    assert correction.type == "correction"
    assert correction.amount == Decimal("10.00")
    assert correction.from_party == "shop"
    assert correction.to_party == "rider"
    assert correction.reason == payload["reason"]
    assert correction.created_by == admin
    assert AuditLog.objects.filter(
        target_type="cash.cashrecord",
        target_id=str(correction.pk),
        what="cash.recorded",
        who=admin,
    ).exists()


def test_order_cash_sums(order, admin_and_clients) -> None:
    require_cash_module("cash.services")
    admin, admin_client, regular_client = admin_and_clients
    for transfer in [
        ("customer_payment", "1000.00", "customer", "rider"),
        ("change", "401.00", "rider", "customer"),
        ("shop_payout", "540.00", "rider", "shop"),
    ]:
        add_cash(
            order=order,
            actor=admin,
            type=transfer[0],
            amount=transfer[1],
            from_party=transfer[2],
            to_party=transfer[3],
        )

    path = f"/api/admin/orders/{order.pk}/cash"
    assert regular_client.get(path).status_code == 403
    response = admin_client.get(path)

    assert response.status_code == 200
    assert response.data["order"] == order.pk
    assert response.data["balances"] == {
        "customer": "-599.00",
        "rider": "59.00",
        "shop": "540.00",
    }
    assert sum(Decimal(value) for value in response.data["balances"].values()) == 0
    assert len(response.data["records"]) == 3


def test_cash_endpoints_match_openapi_contract(migrated_database) -> None:
    import schemathesis
    from django.core.wsgi import get_wsgi_application

    schema = schemathesis.openapi.from_wsgi(
        "/api/schema/?format=json",
        get_wsgi_application(),
    )

    get_case = schema["/api/admin/orders/{id}/cash"]["GET"].Case(
        path_parameters={"id": 1}
    )
    assert get_case.call().status_code in {200, 403, 404}

    post_case = schema["/api/admin/cash/corrections"]["POST"].Case(
        body={
            "order": 1,
            "amount": "10.00",
            "from": "shop",
            "to": "rider",
            "reason": "Correct an earlier cash line.",
        },
    )
    assert post_case.call().status_code in {201, 400, 403, 404}
