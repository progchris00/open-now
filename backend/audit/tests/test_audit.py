from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[3]


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
def admin_client(migrated_database):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    user, _ = get_user_model().objects.get_or_create(
        username="audit-admin",
        defaults={
            "password": "test-password",
            "email": "audit-admin@example.com",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    client = APIClient()
    client.force_authenticate(user=user)
    try:
        yield client, user
    finally:
        from audit.models import AuditLog, CashRecord, Order

        CashRecord.objects.all().delete()
        AuditLog.objects.all().delete()
        Order.objects.all().delete()
        user.delete()


@pytest.fixture(autouse=True)
def clean_audit_data(migrated_database) -> None:
    from audit.models import AuditLog, CashRecord, Order

    CashRecord.objects.all().delete()
    AuditLog.objects.all().delete()
    Order.objects.all().delete()


def test_status_change_writes_audit(admin_client) -> None:
    from audit.models import AuditLog, Order

    client, admin = admin_client
    order = Order.objects.create(status="pending")

    order.status = "accepted"
    order.save(actor=admin)

    entry = AuditLog.objects.get()
    assert entry.who == admin
    assert entry.what == "order.status"
    assert entry.before == "pending"
    assert entry.after == "accepted"
    assert entry.when is not None


def test_cash_record_writes_audit(admin_client) -> None:
    from audit.models import AuditLog, CashRecord

    client, admin = admin_client
    CashRecord.objects.create(actor=admin, label="cash-on-delivery")

    entry = AuditLog.objects.get()
    assert entry.who == admin
    assert entry.what == "cash.record"
    assert entry.before is None
    assert entry.after == "cash-on-delivery"


def test_audit_entries_are_read_only(admin_client) -> None:
    from audit.models import AuditLog, CashRecord

    client, admin = admin_client
    CashRecord.objects.create(actor=admin, label="cash-on-delivery")
    entry = AuditLog.objects.get()

    with pytest.raises(PermissionError):
        entry.after = "changed"
        entry.save()

    with pytest.raises(PermissionError):
        entry.delete()


def test_audit_endpoint_is_admin_only(admin_client) -> None:
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    client, _ = admin_client
    assert client.get("/api/admin/audit").status_code == 200

    user = get_user_model().objects.create_user(
        username="audit-user",
        password="test-password",
    )
    regular_client = APIClient()
    regular_client.force_authenticate(user=user)
    assert regular_client.get("/api/admin/audit").status_code == 403

    user.delete()


def test_status_endpoint_writes_audit(admin_client) -> None:
    from audit.models import AuditLog, Order

    client, admin = admin_client
    order = Order.objects.create(status="pending")

    response = client.patch(
        f"/api/admin/orders/{order.pk}/status",
        {"status": "completed"},
        format="json",
    )

    assert response.status_code == 200
    entry = AuditLog.objects.get()
    assert entry.who == admin
    assert entry.before == "pending"
    assert entry.after == "completed"


def test_cash_endpoint_writes_append_only_record(admin_client) -> None:
    from audit.models import AuditLog, CashRecord

    client, admin = admin_client
    response = client.post(
        "/api/admin/cash-records",
        {"label": "cash-on-delivery"},
        format="json",
    )

    assert response.status_code == 201
    record = CashRecord.objects.get()
    assert record.actor == admin
    assert AuditLog.objects.get().after == "cash-on-delivery"

    with pytest.raises(PermissionError):
        record.delete()
