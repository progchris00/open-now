from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

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

    user = get_user_model().objects.create_superuser(
        username=f"audit-admin-{uuid4().hex}",
        password="test-password",
        email=f"audit-admin-{uuid4().hex}@example.com",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture(autouse=True)
def clean_audit_data(migrated_database) -> None:
    from django.db import transaction

    with transaction.atomic():
        yield
        transaction.set_rollback(True)


def test_record_stores_target_and_change(admin_client) -> None:
    from audit.log import record
    from audit.models import AuditLog

    _, admin = admin_client
    entry = record(
        who=admin,
        what="order.status",
        target=admin,
        before="pending",
        after="accepted",
    )

    assert entry == AuditLog.objects.get(pk=entry.pk)
    assert entry.who == admin
    assert entry.what == "order.status"
    assert entry.target_type == "auth.user"
    assert entry.target_id == str(admin.pk)
    assert entry.before == "pending"
    assert entry.after == "accepted"
    assert entry.when is not None


def test_setting_change_writes_audit(admin_client) -> None:
    from audit.models import AuditLog

    client, admin = admin_client
    response = client.patch(
        "/api/admin/settings/service_fee_per_order",
        {"value": 7},
        format="json",
    )

    assert response.status_code == 200
    entry = AuditLog.objects.get(
        who=admin,
        target_type="settings_store.setting",
        target_id="service_fee_per_order",
        what="setting.value",
        before=5,
        after=7,
    )
    assert entry.who == admin
    assert (entry.before, entry.after) == (5, 7)


def test_system_entries_are_displayed_and_can_be_filtered(admin_client) -> None:
    from django.contrib.auth import get_user_model

    from audit.log import record

    client, admin = admin_client
    other_target = get_user_model().objects.create_user(
        username=f"audit-target-{uuid4().hex}",
    )
    record(
        who=None,
        what="order.status",
        target=admin,
        before="pending",
        after="cancelled",
    )
    record(
        who=admin,
        what="cash.record",
        target=other_target,
        after={"amount": "10.00"},
    )

    response = client.get(
        "/api/admin/audit",
        {"target_type": "auth.user", "target_id": admin.pk},
    )

    assert response.status_code == 200
    assert len(response.data) == 1
    entry = response.data[0]
    assert entry["who"] is None
    assert entry["who_label"] == "System"
    assert entry["what"] == "order.status"
    assert entry["target_type"] == "auth.user"
    assert entry["target_id"] == str(admin.pk)


def test_audit_entries_are_read_only(admin_client) -> None:
    from audit.log import record
    from audit.models import AuditLog

    client, admin = admin_client
    entry = record(
        who=admin,
        what="cash.record",
        target=admin,
        after="cash-on-delivery",
    )

    with pytest.raises(PermissionError):
        entry.after = "changed"
        entry.save()

    with pytest.raises(PermissionError):
        entry.delete()

    with pytest.raises(PermissionError):
        AuditLog.objects.filter(pk=entry.pk).update(after="changed")

    with pytest.raises(PermissionError):
        AuditLog.objects.filter(pk=entry.pk).delete()

    assert client.patch("/api/admin/audit", {"after": "changed"}).status_code == 405
    assert client.delete("/api/admin/audit").status_code == 405


def test_audit_endpoint_is_admin_only_and_other_write_routes_are_absent(
    admin_client,
) -> None:
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    client, _ = admin_client
    assert client.get("/api/admin/audit").status_code == 200
    assert client.patch("/api/admin/orders/1/status").status_code == 404
    assert client.post("/api/admin/cash-records").status_code == 404

    user = get_user_model().objects.create_user(
        username=f"audit-user-{uuid4().hex}",
        password="test-password",
    )
    regular_client = APIClient()
    regular_client.force_authenticate(user=user)
    assert regular_client.get("/api/admin/audit").status_code == 403


def test_audit_contract_covers_read_endpoint() -> None:
    import schemathesis
    from django.core.wsgi import get_wsgi_application

    configure_django()
    schema = schemathesis.openapi.from_wsgi(
        "/api/schema/?format=json",
        get_wsgi_application(),
    )
    operation = schema["/api/admin/audit"]["GET"]
    case = operation.Case(
        query={"target_type": "auth.user", "target_id": "1"},
    )
    response = case.call()
    assert response.status_code in {200, 403}
