"""Small Semaphore API client using only Python's standard library."""

from __future__ import annotations

import json
from urllib import error, parse, request

from django.conf import settings

from settings_store.cache import get_setting

REGULAR_URL = "https://api.semaphore.co/api/v4/messages"
PRIORITY_URL = "https://api.semaphore.co/api/v4/priority"
FAILED_PROVIDER_STATUSES = {"failed", "refunded"}


class SemaphoreError(RuntimeError):
    pass


def send_message(*, to: str, message: str, priority: bool) -> dict[str, object]:
    api_key = settings.SEMAPHORE_API_KEY
    if not api_key:
        raise SemaphoreError("The Semaphore API key is not configured.")

    fields = {"apikey": api_key, "number": to, "message": message}
    if settings.SEMAPHORE_SENDER_NAME:
        fields["sendername"] = settings.SEMAPHORE_SENDER_NAME

    outbound = request.Request(
        PRIORITY_URL if priority else REGULAR_URL,
        data=parse.urlencode(fields).encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    timeout = int(get_setting("sms_request_timeout_seconds"))
    try:
        with request.urlopen(outbound, timeout=timeout) as response:
            payload = json.loads(response.read().decode())
    except (
        error.HTTPError,
        error.URLError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise SemaphoreError(f"Semaphore request failed: {exc}") from exc

    if not isinstance(payload, list) or not payload:
        raise SemaphoreError("Semaphore returned an invalid response.")
    message_result = payload[0]
    if not isinstance(message_result, dict):
        raise SemaphoreError("Semaphore returned an invalid message result.")

    provider_status = str(message_result.get("status", "")).lower()
    if not message_result.get("message_id") or not provider_status:
        raise SemaphoreError("Semaphore returned an incomplete message result.")
    if provider_status in FAILED_PROVIDER_STATUSES:
        raise SemaphoreError(f"Semaphore marked the message {provider_status}.")
    return message_result
