"""Internal SMS task. There is deliberately no user-facing API route."""

from __future__ import annotations

from celery import shared_task

from settings_store.cache import get_setting

from .models import SmsLog
from .semaphore import SemaphoreError, send_message

LOGIN_CODE_TEMPLATE = "login_code"


def retry_delay(retry_number: int) -> int:
    base = int(get_setting("sms_retry_backoff_seconds"))
    multiplier = int(get_setting("sms_retry_backoff_multiplier"))
    return base * multiplier**retry_number


@shared_task(bind=True)
def send_sms(
    self,
    *,
    event_key: str,
    to: str,
    template: str,
    message: str,
    order_id: int | None = None,
) -> str:
    """Send one transactional text per event key and keep its complete outcome."""
    log, created = SmsLog.objects.get_or_create(
        event_key=event_key,
        defaults={
            "to": to,
            "template": template,
            "order_id": order_id,
            "status": SmsLog.Status.PENDING,
        },
    )
    retry_number = self.request.retries
    if not created and (
        retry_number == 0
        or log.status in {SmsLog.Status.SENT, SmsLog.Status.FAILED}
    ):
        return log.status

    log.attempts += 1
    try:
        result = send_message(
            to=log.to,
            message=message,
            priority=log.template == LOGIN_CODE_TEMPLATE,
        )
    except SemaphoreError as exc:
        log.last_error = str(exc)
        max_retries = int(get_setting("sms_max_retries"))
        if retry_number < max_retries:
            log.status = SmsLog.Status.RETRYING
            log.save(update_fields=["attempts", "last_error", "status", "updated_at"])
            raise self.retry(
                exc=exc,
                countdown=retry_delay(retry_number),
                max_retries=max_retries,
            )

        log.status = SmsLog.Status.FAILED
        log.save(update_fields=["attempts", "last_error", "status", "updated_at"])
        return log.status

    log.status = SmsLog.Status.SENT
    log.provider_message_id = str(result["message_id"])
    log.last_error = ""
    log.save(
        update_fields=[
            "attempts",
            "last_error",
            "provider_message_id",
            "status",
            "updated_at",
        ]
    )
    return log.status
