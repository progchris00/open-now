from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def configure_django() -> None:
    settings_file = BACKEND_ROOT / "config" / "settings.py"

    assert settings_file.is_file(), (
        "Django has not been scaffolded in backend/config yet"
    )

    sys.path.insert(0, str(BACKEND_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()


def test_health_endpoint_returns_ok() -> None:
    configure_django()

    from django.test import Client

    response = Client().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "postgis": "ok",
    }


def test_database_has_postgis_extension() -> None:
    configure_django()

    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT extversion "
            "FROM pg_extension "
            "WHERE extname = 'postgis'"
        )
        postgis_version = cursor.fetchone()

    assert postgis_version is not None


def test_health_endpoint_returns_unavailable_when_database_fails() -> None:
    configure_django()

    from django.db import DatabaseError
    from django.test import Client

    with patch("core.views.connection.cursor", side_effect=DatabaseError):
        response = Client().get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "database": "unavailable",
        "postgis": "unknown",
    }


def test_health_endpoint_returns_unavailable_without_postgis() -> None:
    configure_django()

    from django.test import Client

    cursor_context = MagicMock()
    cursor_context.__enter__.return_value.fetchone.return_value = (False,)

    with patch("core.views.connection.cursor", return_value=cursor_context):
        response = Client().get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "database": "unavailable",
        "postgis": "unknown",
    }
