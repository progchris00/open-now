"""Property tests for S2-09 cash-ledger arithmetic."""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

from hypothesis import example, given
from hypothesis import strategies as st

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

parties = st.sampled_from(["customer", "rider", "shop", "coordinator"])
amounts = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("99999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)
transfers = st.lists(
    st.tuples(parties, parties, amounts).filter(lambda row: row[0] != row[1]),
    min_size=1,
    max_size=30,
)


@given(lines=transfers)
@example(
    lines=[
        ("customer", "rider", Decimal("1000.00")),
        ("rider", "customer", Decimal("401.00")),
        ("rider", "shop", Decimal("540.00")),
    ]
)
def test_balance_equals_sum_of_lines(lines) -> None:
    assert importlib.util.find_spec("cash.math") is not None, (
        "Cash balance maths have not been implemented yet"
    )
    from cash.math import summarize_balances

    balances = summarize_balances(lines)
    all_parties = {party for line in lines for party in line[:2]}

    for party in all_parties:
        expected = sum(
            (
                amount if to_party == party else -amount if from_party == party else 0
                for from_party, to_party, amount in lines
            ),
            Decimal("0.00"),
        )
        assert balances[party] == expected

    assert sum(balances.values(), Decimal("0.00")) == Decimal("0.00")
    if lines == [
        ("customer", "rider", Decimal("1000.00")),
        ("rider", "customer", Decimal("401.00")),
        ("rider", "shop", Decimal("540.00")),
    ]:
        assert balances == {
            "customer": Decimal("-599.00"),
            "rider": Decimal("59.00"),
            "shop": Decimal("540.00"),
        }
