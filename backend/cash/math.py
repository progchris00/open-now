"""Pure arithmetic for the append-only cash ledger."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

Transfer = tuple[str, str, Decimal]


def summarize_balances(lines: Iterable[Transfer]) -> dict[str, Decimal]:
    """Return incoming minus outgoing cash for every party in the lines."""
    balances: dict[str, Decimal] = {}
    for from_party, to_party, amount in lines:
        balances.setdefault(from_party, Decimal("0.00"))
        balances.setdefault(to_party, Decimal("0.00"))
        balances[from_party] -= amount
        balances[to_party] += amount
    return balances
