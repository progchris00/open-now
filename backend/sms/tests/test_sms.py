"""S1-14: Semaphore SMS delivery, logging, retries and deduplication."""

from __future__ import annotations

import importlib
import importlib.util
import json
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


def sms_module(name: str):
    """Fail with the intended missing-feature assertion, not an import error."""
    assert importlib.util.find_spec(name) is not None, (
        f"The S1-14 module {name!r} has not been implemented yet"
    )
    return importlib.import_module(name)


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    configure_django()

    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)


@pytest.fixture
def rollback(migrated_database):
    from django.db import transaction

    from settings_store.cache import invalidate_settings_cache

    invalidate_settings_cache()
    with transaction.atomic():
        yield
        transaction.set_rollback(True)
    invalidate_settings_cache()


@pytest.fixture
def order(rollback):
    from django.contrib.auth import get_user_model

    from orders.models import Order

    customer = get_user_model().objects.create_user(username=f"sms-{uuid4().hex}")
    return Order.objects.create(
        customer=customer,
        shop_id=1,
        items_total=Decimal("100.00"),
        delivery_fee=Decimal("50.00"),
        service_fee=Decimal("5.00"),
        discount=Decimal("0.00"),
        total=Decimal("155.00"),
        bill=Decimal("200.00"),
        change=Decimal("45.00"),
        idempotency_key=uuid4().hex,
        request_fingerprint=uuid4().hex + uuid4().hex,
    )


def set_sms_settings(**values: object) -> None:
    from settings_store.cache import invalidate_settings_cache
    from settings_store.models import Setting

    for key, value in values.items():
        updated = Setting.objects.filter(key=key).update(value=value)
        assert updated == 1, f"Setting {key!r} is not seeded"
    invalidate_settings_cache()


def task_kwargs(*, event_key: str = "order-placed:1", order_id: int | None = None):
    return {
        "event_key": event_key,
        "to": "09171234567",
        "template": "order_placed",
        "message": "Your OpenNow order has been placed.",
        "order_id": order_id,
    }


def accepted_message() -> dict[str, object]:
    return {"message_id": 12345, "status": "Queued", "type": "single"}


def test_send_logs_message(rollback, order, monkeypatch) -> None:
    models = sms_module("sms.models")
    tasks = sms_module("sms.tasks")
    monkeypatch.setattr(tasks, "send_message", lambda **kwargs: accepted_message())

    result = tasks.send_sms.run(**task_kwargs(order_id=order.pk))

    log = models.SmsLog.objects.get(event_key="order-placed:1")
    assert result == models.SmsLog.Status.SENT
    assert log.to == "09171234567"
    assert log.template == "order_placed"
    assert log.order == order
    assert log.status == models.SmsLog.Status.SENT
    assert log.attempts == 1
    assert log.provider_message_id == "12345"


def test_retry_on_failure(rollback, monkeypatch) -> None:
    models = sms_module("sms.models")
    semaphore = sms_module("sms.semaphore")
    tasks = sms_module("sms.tasks")
    set_sms_settings(
        sms_max_retries=2,
        sms_retry_backoff_seconds=3,
        sms_retry_backoff_multiplier=2,
    )
    calls = []

    def unavailable(**kwargs):
        calls.append(kwargs)
        raise semaphore.SemaphoreError("Semaphore is unavailable")

    monkeypatch.setattr(tasks, "send_message", unavailable)

    result = tasks.send_sms.apply(kwargs=task_kwargs(event_key="retry-me"))

    log = models.SmsLog.objects.get(event_key="retry-me")
    assert result.successful()
    assert result.result == models.SmsLog.Status.FAILED
    assert len(calls) == 3
    assert log.status == models.SmsLog.Status.FAILED
    assert log.attempts == 3
    assert log.last_error == "Semaphore is unavailable"
    assert tasks.retry_delay(0) == 3
    assert tasks.retry_delay(1) == 6


def test_dedupe_same_event(rollback, monkeypatch) -> None:
    models = sms_module("sms.models")
    tasks = sms_module("sms.tasks")
    calls = []

    def accepted(**kwargs):
        calls.append(kwargs)
        return accepted_message()

    monkeypatch.setattr(tasks, "send_message", accepted)
    values = task_kwargs(event_key="same-event")

    first = tasks.send_sms.run(**values)
    second = tasks.send_sms.run(**values)

    assert (first, second) == (models.SmsLog.Status.SENT, models.SmsLog.Status.SENT)
    assert len(calls) == 1
    assert models.SmsLog.objects.filter(event_key="same-event").count() == 1


def test_login_code_uses_priority_route(rollback, monkeypatch) -> None:
    tasks = sms_module("sms.tasks")
    calls = []

    def accepted(**kwargs):
        calls.append(kwargs)
        return accepted_message()

    monkeypatch.setattr(tasks, "send_message", accepted)

    tasks.send_sms.run(
        **{
            **task_kwargs(event_key="login-code:1"),
            "template": "login_code",
            "message": "Your OpenNow login code is 123456.",
        }
    )

    assert calls == [
        {
            "to": "09171234567",
            "message": "Your OpenNow login code is 123456.",
            "priority": True,
        }
    ]


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_semaphore_uses_official_routes_and_admin_timeout(
    rollback, monkeypatch
) -> None:
    semaphore = sms_module("sms.semaphore")
    set_sms_settings(sms_request_timeout_seconds=7)
    monkeypatch.setattr(semaphore.settings, "SEMAPHORE_API_KEY", "secret")
    monkeypatch.setattr(semaphore.settings, "SEMAPHORE_SENDER_NAME", "OpenNow")
    calls = []

    def urlopen(request, *, timeout):
        calls.append((request.full_url, request.data, timeout))
        return FakeResponse([accepted_message()])

    monkeypatch.setattr(semaphore.request, "urlopen", urlopen)

    regular = semaphore.send_message(to="09171234567", message="Update", priority=False)
    priority = semaphore.send_message(to="09171234567", message="Code", priority=True)

    assert regular["message_id"] == priority["message_id"] == 12345
    assert [url for url, _, _ in calls] == [
        "https://api.semaphore.co/api/v4/messages",
        "https://api.semaphore.co/api/v4/priority",
    ]
    assert [timeout for _, _, timeout in calls] == [7, 7]
    assert all(b"apikey=secret" in data for _, data, _ in calls)
    assert all(b"sendername=OpenNow" in data for _, data, _ in calls)


@pytest.mark.parametrize(
    "payload",
    [[], [{"message_id": 1, "status": "Failed"}], {"unexpected": "object"}],
)
def test_semaphore_refuses_failed_or_invalid_responses(
    rollback, monkeypatch, payload
) -> None:
    semaphore = sms_module("sms.semaphore")
    set_sms_settings(sms_request_timeout_seconds=7)
    monkeypatch.setattr(semaphore.settings, "SEMAPHORE_API_KEY", "secret")
    monkeypatch.setattr(semaphore.settings, "SEMAPHORE_SENDER_NAME", "")
    monkeypatch.setattr(
        semaphore.request,
        "urlopen",
        lambda request, *, timeout: FakeResponse(payload),
    )

    with pytest.raises(semaphore.SemaphoreError):
        semaphore.send_message(to="09171234567", message="Update", priority=False)


def test_semaphore_requires_api_key(rollback, monkeypatch) -> None:
    semaphore = sms_module("sms.semaphore")
    monkeypatch.setattr(semaphore.settings, "SEMAPHORE_API_KEY", "")

    with pytest.raises(semaphore.SemaphoreError, match="API key"):
        semaphore.send_message(to="09171234567", message="Update", priority=False)
