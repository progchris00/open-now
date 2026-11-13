from __future__ import annotations

from pathlib import Path

from django.db import DatabaseError, connection
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'postgis'"
            )
            postgis = cursor.fetchone()
    except DatabaseError:
        return JsonResponse(
            {"status": "error", "database": "error", "postgis": "error"},
            status=503,
        )

    if postgis is None:
        return JsonResponse(
            {"status": "error", "database": "ok", "postgis": "missing"},
            status=503,
        )

    return JsonResponse({"status": "ok", "database": "ok", "postgis": "ok"})


@require_GET
def openapi_schema(request) -> FileResponse:
    contract = Path(__file__).resolve().parent.parent / "openapi.yaml"
    return FileResponse(contract.open("rb"), content_type="application/yaml")
