"""Accept and reject as a state machine (S2-15.1), checked with Hypothesis.

Hypothesis builds random sequences of merchant actions: accept, reject,
repeat either one, and let the clock run on. Each sequence runs against the
real service and database, and every answer is compared with a small
reference model of the rules:

- from New, the first accept or reject inside the deadline wins;
- repeating the winning decision changes nothing and is not an error;
- anything else is refused, and the deadline is refused while still New;
- after every sequence there is exactly one history row per status the
  order went through, so nothing was written twice.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

ACCEPT_MINUTES = 5

actions = st.lists(
    st.one_of(
        st.just(("accept", None)),
        st.tuples(st.just("reject"), st.sampled_from(["Closed", "Out of rice"])),
        st.tuples(st.just("wait"), st.integers(min_value=1, max_value=4)),
    ),
    min_size=1,
    max_size=8,
)


def expected(status: str, reason: str, elapsed: int, action: str, arg):
    """The reference model. Returns (new_status, new_reason, outcome)."""
    target = {"accept": "accepted", "reject": "rejected"}[action]
    if status == target and (target == "accepted" or arg == reason):
        return status, reason, "unchanged"
    if status != "new":
        return status, reason, "not_allowed"
    if elapsed > ACCEPT_MINUTES:
        return status, reason, "deadline_passed"
    return target, (arg or ""), "changed"


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(steps=actions)
@example(steps=[("accept", None), ("accept", None), ("reject", "Closed")])
@example(steps=[("wait", 4), ("wait", 2), ("accept", None)])
@example(steps=[("reject", "Closed"), ("reject", "Out of rice")])
def test_decisions_follow_the_rules(steps, merchant, place, set_settings) -> None:
    from django.db import transaction

    from orders.transitions import TransitionError, transition

    set_settings(accept_minutes=ACCEPT_MINUTES)
    with transaction.atomic():
        order, _ = place()
        status, reason, elapsed, path = "new", "", 0, ["new"]

        for action, arg in steps:
            if action == "wait":
                elapsed += arg
                continue

            status, reason, outcome = expected(status, reason, elapsed, action, arg)
            to = {"accept": "accepted", "reject": "rejected"}[action]
            now = order.created_at + timedelta(minutes=elapsed)
            try:
                result, changed = transition(
                    order_id=order.pk, to=to, by=merchant, reason=arg or "", now=now
                )
            except TransitionError as error:
                assert outcome == error.code, (steps, action)
            else:
                assert outcome == ("changed" if changed else "unchanged"), (
                    steps,
                    action,
                )
                assert result.status == status
            if outcome == "changed":
                path.append(status)

        order.refresh_from_db()
        assert order.status == status
        assert [row.status for row in order.status_history.all()] == path
        transaction.set_rollback(True)


@pytest.mark.parametrize(
    ("status", "action", "outcome"),
    [
        ("new", "accept", "changed"),
        ("accepted", "accept", "unchanged"),
        ("accepted", "reject", "not_allowed"),
        ("rejected", "accept", "not_allowed"),
    ],
)
def test_reference_model_matches_the_card(status, action, outcome) -> None:
    assert expected(status, "", 0, action, "Closed")[2] == outcome
