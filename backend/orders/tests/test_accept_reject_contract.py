"""The accept and reject endpoints match the OpenAPI contract (S2-15.1).

The schema is the one drf-spectacular serves, the same source CI checks and
backend/openapi.yaml is generated from. Schemathesis calls each operation
and validates the status code, headers and body against it.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def schema(migrated_database):
    import schemathesis
    from django.core.wsgi import get_wsgi_application

    return schemathesis.openapi.from_wsgi(
        "/api/schema/?format=json", get_wsgi_application()
    )


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/merchant/orders/{id}/accept", None),
        ("/api/merchant/orders/{id}/reject", {"reason": "Closed"}),
    ],
)
def test_anonymous_call_matches_contract(schema, path, body) -> None:
    operation = schema[path]["POST"]
    kwargs = {"path_parameters": {"id": 1}}
    if body is not None:
        kwargs["body"] = body
    case = operation.Case(**kwargs)

    response = case.call_and_validate()
    assert response.status_code == 403


def test_contract_documents_every_answer(schema) -> None:
    for path in (
        "/api/merchant/orders/{id}/accept",
        "/api/merchant/orders/{id}/reject",
    ):
        responses = schema[path]["POST"].definition.raw["responses"]
        assert {"200", "403", "409"} <= set(responses), path
    reject = schema["/api/merchant/orders/{id}/reject"]["POST"].definition.raw
    assert "400" in reject["responses"]


def test_committed_contract_file_lists_the_endpoints() -> None:
    from pathlib import Path

    contract = (Path(__file__).resolve().parents[2] / "openapi.yaml").read_text(
        encoding="utf-8"
    )
    assert "/api/merchant/orders/{id}/accept:" in contract
    assert "/api/merchant/orders/{id}/reject:" in contract
