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
    """The POST /api/orders operation, called in-process through WSGI.

    Django closes the database connection at the end of every WSGI request,
    which would drop the test's rolled-back transaction. Django's own test
    client switches that off for the same reason, and so does this fixture.
    """
    import schemathesis
    from django.core.signals import request_finished, request_started
    from django.core.wsgi import get_wsgi_application
    from django.db import close_old_connections

    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    try:
        schema = schemathesis.openapi.from_wsgi(
            "/api/schema/?format=json",
            get_wsgi_application(),
        )
        yield schema["/api/orders"]["POST"]
    finally:
        request_started.connect(close_old_connections)
        request_finished.connect(close_old_connections)


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
        media_type="application/json",
        headers={
            "Idempotency-Key": "contract-sample",
            "Authorization": basic_auth(customer),
        },
    )

    response = case.call_and_validate()

    assert response.status_code == 201


def test_anonymous_request_matches_the_schema(operation, sample_request) -> None:
    case = operation.Case(
        body=sample_request,
        media_type="application/json",
        headers={"Idempotency-Key": "anonymous"},
    )

    response = case.call_and_validate()

    assert response.status_code == 403


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(data=st.data())
def test_generated_requests_never_break_the_contract(operation, menu, data) -> None:
    """Customer requests built from the schema get documented answers only.

    Two checks are left out on purpose:
    - positive_data_acceptance: a request can match the schema and still name
      a product that doesn't exist, which is correctly refused with 400.
    - ignored_auth: this test signs in by adding the Authorization header
      itself, which Schemathesis can't strip, so its "invalid credentials"
      retry still carries valid ones. test_anonymous_gets_403 and
      test_non_customer_gets_403 cover authentication instead.
    Every other check (no server error, documented status codes, response
    bodies that match the schema) still runs.
    """
    from schemathesis.checks import ignored_auth, positive_data_acceptance

    customer = make_user(customer=True)
    case = data.draw(operation.as_strategy())
    case.headers = {**(case.headers or {}), "Authorization": basic_auth(customer)}

    case.call_and_validate(excluded_checks=[positive_data_acceptance, ignored_auth])


def test_schema_states_the_request_rules(migrated_database) -> None:
    """The published schema refuses what the API refuses."""
    from rest_framework.test import APIClient

    schema = APIClient().get("/api/schema/?format=json").json()
    components = schema["components"]["schemas"]
    properties = dict(components["PlaceOrder"]["properties"])
    method_ref = properties["payment_method"]["allOf"][0]["$ref"]
    properties["payment_method"] = components[method_ref.rsplit("/", 1)[-1]]

    assert properties["items"]["minItems"] == 1
    line = components["PlaceOrderLine"]["properties"]
    assert line["quantity"]["maximum"] == 2147483647
    assert properties["payment_method"]["enum"] == ["cod"]
    for name in ("bill", "distance_km"):
        assert not properties[name]["pattern"].startswith("^-"), name
