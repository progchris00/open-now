from decimal import Decimal

from rest_framework import serializers

from orders.models import MONEY, Order

from .models import CashRecord


class PartyAliasesMixin:
    """Expose Python-safe model names as the contract's `from` and `to`."""

    def get_fields(self):
        fields = super().get_fields()
        fields["from"] = serializers.ChoiceField(
            source="from_party",
            choices=CashRecord.Party.choices,
        )
        fields["to"] = serializers.ChoiceField(
            source="to_party",
            choices=CashRecord.Party.choices,
        )
        return fields


class CashRecordSerializer(PartyAliasesMixin, serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    order = serializers.IntegerField(source="order_id", read_only=True)
    type = serializers.ChoiceField(choices=CashRecord.Type.choices, read_only=True)
    amount = serializers.DecimalField(
        max_digits=MONEY["max_digits"],
        decimal_places=MONEY["decimal_places"],
        read_only=True,
    )
    created_by = serializers.IntegerField(
        source="created_by_id",
        read_only=True,
        allow_null=True,
    )
    reason = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class CashCorrectionSerializer(PartyAliasesMixin, serializers.Serializer):
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    amount = serializers.DecimalField(
        max_digits=MONEY["max_digits"],
        decimal_places=MONEY["decimal_places"],
        min_value=Decimal("0.01"),
    )
    reason = serializers.CharField(min_length=1, trim_whitespace=True)

    def validate(self, attrs):
        if attrs["from_party"] == attrs["to_party"]:
            raise serializers.ValidationError(
                {"to": "The receiving party must differ from the sending party."}
            )
        return attrs


class OrderCashSerializer(serializers.Serializer):
    order = serializers.IntegerField()
    records = CashRecordSerializer(many=True)
    balances = serializers.DictField(
        child=serializers.DecimalField(
            max_digits=MONEY["max_digits"],
            decimal_places=MONEY["decimal_places"],
        )
    )
