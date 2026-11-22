"""Schemathesis: POST /api/orders matches the published schema (S2-12.1).

The schema is the one Django serves at /api/schema/, the same source the
existing contract test uses. Every response, including errors, must match
what the schema documents, and no input may cause a server error.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from .conftest import basic_auth, make_user


@pytest.fixture
def operation(migrated_database):
    import schemathesis
    from django.core.wsgi import get_wsgi_application

    schema = schemathesis.openapi.from_wsgi(
        "/api/schema/?format=json",
        get_wsgi_application(),
    )
    return schema["/api/orders"]["POST"]


def test_schema_documents_every_response(operation) -> None:
    documented = set(operation.definition.raw["responses"])

    assert {"200", "201", "400", "403", "409"} <= documented
    header_names = {
        parameter["name"]
        for parameter in operation.definition.raw.get("parameters", [])
        if parameter["in"] == "header"
    }
    assert "Idempotency-Key" in header_names


def test_sample_order_matches_the_schema(operation, customer, sample_request) -> None:
    case = operation.Case(
        body=sample_request,
        headers={
            "Idempotency-Key": "contract-sample",
            "Authorization": basic_auth(customer),
        },
    )

    response = case.call_and_validate()

    assert response.status_code == 201


def test_anonymous_request_matches_the_schema(operation, sample_request) -> None:
    case = operation.Case(body=sample_request, headers={"Idempotency-Key": "anonymous"})

    response = case.call_and_validate()

    assert response.status_code == 403


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(data=st.data())
def test_generated_requests_never_break_the_contract(operation, menu, data) -> None:
    """Customer requests built from the schema get documented answers only."""
    customer = make_user(customer=True)
    case = data.draw(operation.as_strategy())
    case.headers = {**(case.headers or {}), "Authorization": basic_auth(customer)}

    case.call_and_validate()
