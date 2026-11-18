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


def test_status_change_writes_audit(admin_client) -> None:
    from audit.models import AuditLog, Order

    _, admin = admin_client
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

    _, admin = admin_client
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
    response = client.get("/api/admin/audit")

    assert response.status_code == 200
    serialized = response.json()[0]
    assert serialized["who"] == admin.pk
    assert serialized["what"] == "cash.record"
    assert serialized["before"] is None
    assert serialized["after"] == "cash-on-delivery"
    assert serialized["when"]

    entry = AuditLog.objects.get()

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


def test_audit_endpoint_is_admin_only(admin_client) -> None:
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    client, _ = admin_client
    assert client.get("/api/admin/audit").status_code == 200

    user = get_user_model().objects.create_user(
        username=f"audit-user-{uuid4().hex}",
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

    with pytest.raises(PermissionError):
        CashRecord.objects.filter(pk=record.pk).update(label="changed")

    with pytest.raises(PermissionError):
        CashRecord.objects.filter(pk=record.pk).delete()

    with pytest.raises(PermissionError):
        CashRecord.objects.bulk_create(
            [CashRecord(actor=admin, label="unlogged-cash-record")]
        )


def test_order_status_requires_actor_and_is_saved_before_auditing(admin_client) -> None:
    from audit.models import AuditLog, Order

    _, admin = admin_client
    order = Order.objects.create(status="pending")
    order.save()
    assert not AuditLog.objects.exists()

    order.status = "accepted"

    with pytest.raises(PermissionError):
        order.save()

    order.refresh_from_db()
    assert order.status == "pending"
    assert not AuditLog.objects.exists()

    order.status = "accepted"
    order.save(actor=admin, update_fields=["updated_at"])
    order.refresh_from_db()
    assert order.status == "pending"
    assert not AuditLog.objects.exists()

    with pytest.raises(PermissionError):
        Order.objects.filter(pk=order.pk).update(status="accepted")

    order.status = "accepted"
    order.save(actor=admin)
    entry = AuditLog.objects.get(who=admin)
    assert entry.before == "pending"
    assert entry.after == "accepted"


def test_non_admin_cannot_write_status_or_cash(admin_client) -> None:
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    from audit.models import AuditLog, CashRecord, Order

    _, admin = admin_client
    order = Order.objects.create(status="pending")
    user = get_user_model().objects.create_user(
        username=f"audit-user-{uuid4().hex}",
        password="test-password",
    )
    client = APIClient()
    client.force_authenticate(user=user)

    status_response = client.patch(
        f"/api/admin/orders/{order.pk}/status",
        {"status": "accepted"},
        format="json",
    )
    cash_response = client.post(
        "/api/admin/cash-records",
        {"label": "cash-on-delivery"},
        format="json",
    )

    assert status_response.status_code == 403
    assert cash_response.status_code == 403
    assert Order.objects.get(pk=order.pk).status == "pending"
    assert not CashRecord.objects.filter(actor=user).exists()
    assert not AuditLog.objects.filter(who=admin).exists()


def test_audit_contract_covers_new_endpoints() -> None:
    import schemathesis
    from django.core.wsgi import get_wsgi_application

    configure_django()
    schema = schemathesis.openapi.from_wsgi(
        "/api/schema/?format=json",
        get_wsgi_application(),
    )
    operations = [
        ("/api/admin/audit", "GET", {}),
        ("/api/admin/orders/{id}/status", "PATCH", {"status": "pending"}),
        ("/api/admin/cash-records", "POST", {"label": "cod-test-record"}),
    ]

    for path, method, body in operations:
        operation = schema[path][method]
        options = {"path_parameters": {"id": 1}} if "{id}" in path else {}
        case = (
            operation.Case(**options)
            if method == "GET"
            else operation.Case(
                **options,
                body=body,
                media_type="application/json",
            )
        )
        case.call_and_validate()


def test_order_status_validation_returns_bad_request(admin_client) -> None:
    from audit.models import Order

    client, _ = admin_client
    order = Order.objects.create(status="pending")
    response = client.patch(
        f"/api/admin/orders/{order.pk}/status",
        {"status": "online"},
        format="json",
    )

    assert response.status_code == 400
    assert Order.objects.get(pk=order.pk).status == "pending"


def test_invalid_cash_record_is_rejected(admin_client) -> None:
    client, _ = admin_client
    response = client.post(
        "/api/admin/cash-records",
        {"label": ""},
        format="json",
    )

    assert response.status_code == 400
