from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from audit.log import record
from orders.models import Order

from .models import CashRecord


@transaction.atomic
def record_cash(
    *,
    order: Order,
    type: str,
    amount: Decimal,
    from_party: str,
    to_party: str,
    created_by,
    reason: str | None = None,
) -> CashRecord:
    """Append one cash transfer and its audit entry in the same transaction."""
    cash_record = CashRecord(
        order=order,
        type=type,
        amount=amount,
        from_party=from_party,
        to_party=to_party,
        created_by=created_by,
        reason=reason or "",
    )
    cash_record.full_clean()
    cash_record.save()
    record(
        who=created_by,
        what="cash.recorded",
        target=cash_record,
        after={
            "order": order.pk,
            "type": type,
            "amount": str(amount),
            "from": from_party,
            "to": to_party,
            "reason": cash_record.reason,
        },
    )
    return cash_record


def correct_cash(
    *,
    order: Order,
    amount: Decimal,
    from_party: str,
    to_party: str,
    reason: str,
    created_by,
) -> CashRecord:
    return record_cash(
        order=order,
        type=CashRecord.Type.CORRECTION,
        amount=amount,
        from_party=from_party,
        to_party=to_party,
        reason=reason,
        created_by=created_by,
    )
