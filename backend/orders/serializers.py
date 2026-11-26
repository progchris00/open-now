from rest_framework import serializers

from .models import REJECT_REASON_MAX_LENGTH, Order


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=REJECT_REASON_MAX_LENGTH, trim_whitespace=True, allow_blank=False
    )


class MerchantDecisionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=Order.Status.choices)
    accept_deadline = serializers.DateTimeField()
    reject_reason = serializers.CharField(allow_null=True)


class DecisionErrorSerializer(serializers.Serializer):
    code = serializers.ChoiceField(choices=["not_allowed", "deadline_passed"])
    detail = serializers.CharField()
