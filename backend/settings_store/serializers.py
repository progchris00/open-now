from rest_framework import serializers

from .models import Setting


class SettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Setting
        fields = ["key", "value", "updated_by", "updated_at"]
        read_only_fields = fields


class SettingUpdateSerializer(serializers.Serializer):
    value = serializers.JSONField()
