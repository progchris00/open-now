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
    yield client, user

    user.delete()


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
    record = CashRecord.objects.create(actor=admin, label="cash-on-delivery")

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
