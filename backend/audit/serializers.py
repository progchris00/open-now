from rest_framework import serializers

from .models import AuditLog, CashRecord, Order


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "who", "what", "before", "after", "when"]
        read_only_fields = fields


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.values)


class CashRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashRecord
        fields = ["id", "label", "created_at"]
        read_only_fields = ["id", "created_at"]
