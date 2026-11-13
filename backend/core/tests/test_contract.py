from __future__ import annotations

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).parents[2]


def test_health_endpoint_matches_openapi_contract() -> None:
    settings_file = BACKEND_ROOT / "config" / "settings.py"
    assert settings_file.exists(), "Django project scaffold has not been implemented"

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django
    import schemathesis
    from django.core.wsgi import get_wsgi_application

    django.setup()
    schema = schemathesis.openapi.from_wsgi(
        "/api/schema/",
        get_wsgi_application(),
    )
    operation = schema["/api/health"]["GET"]
    case = operation.Case()

    case.call_and_validate()
