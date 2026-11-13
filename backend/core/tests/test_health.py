from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).parents[2]
SETTINGS_MODULE = "config.settings"


def _configure_django() -> None:
    settings_file = BACKEND_ROOT / "config" / "settings.py"
    assert settings_file.exists(), "Django project scaffold has not been implemented"

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", SETTINGS_MODULE)

    import django

    django.setup()


def test_health_endpoint_returns_ok(django_db_blocker) -> None:
    _configure_django()

    from django.test import Client

    with django_db_blocker.unblock():
        response = Client().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "postgis": "ok",
    }


def test_database_has_postgis_extension(django_db_blocker) -> None:
    _configure_django()

    from django.db import connection

    with django_db_blocker.unblock():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'postgis'"
            )
            row = cursor.fetchone()

    assert row is not None, "PostGIS extension is not installed"


def test_celery_ping_task_returns_pong() -> None:
    from core.tasks import ping

    assert ping.run() == "pong"


def test_health_endpoint_reports_missing_postgis() -> None:
    _configure_django()

    from django.test import Client

    cursor = MagicMock()
    cursor.__enter__.return_value.fetchone.return_value = None

    with patch("core.views.connection.cursor", return_value=cursor):
        response = Client().get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "database": "ok",
        "postgis": "missing",
    }


def test_health_endpoint_reports_database_error() -> None:
    _configure_django()

    from django.db import DatabaseError
    from django.test import Client

    with patch("core.views.connection.cursor", side_effect=DatabaseError):
        response = Client().get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "database": "error",
        "postgis": "error",
    }
