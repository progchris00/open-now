from typing import Any

from django.core.cache import cache

from .models import Setting

SETTINGS_CACHE_KEY = "settings_store.settings"


def get_cached_settings() -> list[dict[str, Any]]:
    return cache.get_or_set(
        SETTINGS_CACHE_KEY,
        lambda: list(
            Setting.objects.order_by("key").values(
                "key",
                "value",
                "updated_by",
                "updated_at",
            )
        ),
    )


def get_setting(key: str) -> Any:
    for setting in get_cached_settings():
        if setting["key"] == key:
            return setting["value"]

    raise Setting.DoesNotExist(f"Setting with key {key!r} does not exist")


def invalidate_settings_cache() -> None:
    cache.delete(SETTINGS_CACHE_KEY)
