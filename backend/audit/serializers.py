from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    who_label = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "who",
            "who_label",
            "what",
            "target_type",
            "target_id",
            "before",
            "after",
            "when",
        ]
        read_only_fields = fields

    def get_who_label(self, obj: AuditLog) -> str:
        return "System" if obj.who is None else str(obj.who)
