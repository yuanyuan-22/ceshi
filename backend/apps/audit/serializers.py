from rest_framework import serializers
from .models import AuditLog


class AuditLogListSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "created_at",
            "action", "method", "path", "status_code",
            "ip", "user_agent", "request_id", "latency_ms",
            "extra",
            "user_id", "username",
        ]