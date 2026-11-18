from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


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

    user = get_user_model().objects.create_user(
        username="settings-admin",
        password="test-password",
        is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    yield client, user

    user.delete()


def _settings_by_key(response) -> dict[str, dict[str, object]]:
    return {setting["key"]: setting for setting in response.json()}


def test_seeded_defaults_match_example_values(admin_client) -> None:
    client, _ = admin_client

    response = client.get("/api/admin/settings")

    assert response.status_code == 200
    settings = _settings_by_key(response)
    assert set(settings) == {
        "payment_method",
        "service_fee_per_order",
        "subscription_monthly",
        "free_months",
        "bill_grace_days",
        "delivery_base_fee",
        "delivery_per_km",
        "senior_pwd_discount_percent",
        "return_fee",
        "limit_new_customer",
        "limit_regular",
        "open_orders_new",
        "open_orders_regular",
        "otp_expiry_minutes",
        "session_days",
        "approval_target_days",
        "checkin_lead_minutes",
        "checkin_reminder_minutes",
        "first_order_autopause_minutes",
        "accept_minutes",
        "unusual_confirm_minutes",
        "offer_minutes",
        "offer_max_tries",
        "no_rider_cancel_minutes",
        "pickup_reassign_minutes",
        "failed_calls",
        "failed_wait_minutes",
    }
    assert settings["service_fee_per_order"]["value"] == 5
    assert settings["payment_method"]["value"] == "cod"


def test_rejects_wrong_type_and_negative_values(admin_client) -> None:
    client, _ = admin_client

    for value in ("abc", -5, True):
        response = client.patch(
            "/api/admin/settings/service_fee_per_order",
            {"value": value},
            format="json",
        )

        assert response.status_code == 400
        settings = _settings_by_key(client.get("/api/admin/settings"))
        assert settings["service_fee_per_order"]["value"] == 5


def test_change_is_audited(admin_client) -> None:
    client, admin = admin_client

    try:
        response = client.patch(
            "/api/admin/settings/service_fee_per_order",
            {"value": 8},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["key"] == "service_fee_per_order"
        assert response.json()["value"] == 8

        from django.contrib.admin.models import CHANGE, LogEntry

        assert LogEntry.objects.filter(
            user=admin,
            object_repr="service_fee_per_order",
            action_flag=CHANGE,
        ).exists()
    finally:
        client.patch(
            "/api/admin/settings/service_fee_per_order",
            {"value": 5},
            format="json",
        )


def test_payment_method_is_locked_to_cod(admin_client) -> None:
    client, _ = admin_client

    response = client.patch(
        "/api/admin/settings/payment_method",
        {"value": "online"},
        format="json",
    )

    assert response.status_code == 400
    settings = _settings_by_key(client.get("/api/admin/settings"))
    assert settings["payment_method"]["value"] == "cod"


def test_settings_cached_and_invalidated(admin_client) -> None:
    client, _ = admin_client
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from settings_store.cache import get_setting

    initial = client.get("/api/admin/settings")
    assert initial.status_code == 200
    assert _settings_by_key(initial)["service_fee_per_order"]["value"] == 5
    assert get_setting("service_fee_per_order") == 5

    with CaptureQueriesContext(connection) as queries:
        repeated = client.get("/api/admin/settings")

    assert repeated.status_code == 200
    assert not any("settings_store_setting" in query["sql"] for query in queries)

    try:
        changed = client.patch(
            "/api/admin/settings/service_fee_per_order",
            {"value": 9},
            format="json",
        )
        assert changed.status_code == 200

        with CaptureQueriesContext(connection) as queries:
            refreshed = client.get("/api/admin/settings")

        assert refreshed.status_code == 200
        assert _settings_by_key(refreshed)["service_fee_per_order"]["value"] == 9
        assert any("settings_store_setting" in query["sql"] for query in queries)
        assert get_setting("service_fee_per_order") == 9
    finally:
        client.patch(
            "/api/admin/settings/service_fee_per_order",
            {"value": 5},
            format="json",
        )


def test_settings_endpoints_are_admin_only() -> None:
    configure_django()

    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    client = APIClient()
    assert client.get("/api/admin/settings").status_code == 403
    assert (
        client.patch(
            "/api/admin/settings/service_fee_per_order",
            {"value": 8},
            format="json",
        ).status_code
        == 403
    )

    user = get_user_model().objects.create_user(
        username="settings-non-admin",
        password="test-password",
    )
    try:
        client.force_authenticate(user=user)
        assert client.get("/api/admin/settings").status_code == 403
        assert (
            client.patch(
                "/api/admin/settings/service_fee_per_order",
                {"value": 8},
                format="json",
            ).status_code
            == 403
        )
    finally:
        user.delete()


def test_settings_endpoints_are_in_the_schemathesis_contract() -> None:
    configure_django()

    import schemathesis
    from django.core.wsgi import get_wsgi_application

    schema = schemathesis.openapi.from_wsgi(
        "/api/schema/?format=json",
        get_wsgi_application(),
    )

    get_settings = schema["/api/admin/settings"]["GET"]
    patch_setting = schema["/api/admin/settings/{key}"]["PATCH"]

    assert get_settings is not None
    assert patch_setting is not None

    case = get_settings.Case()
    case.call_and_validate()

    patch_case = patch_setting.Case()
    patch_case.path_parameters = {"key": "service_fee_per_order"}
    patch_case.body = {"value": 6}
    patch_case.call_and_validate()
