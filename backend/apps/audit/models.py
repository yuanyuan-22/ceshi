from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs"
    )

    action = models.CharField(max_length=128)  # e.g. "qa.ask"
    method = models.CharField(max_length=16, blank=True, default="")
    path = models.CharField(max_length=512, blank=True, default="")
    status_code = models.IntegerField(null=True, blank=True)

    ip = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.CharField(max_length=512, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")

    latency_ms = models.IntegerField(null=True, blank=True)
    extra = models.JSONField(blank=True, default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["request_id"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"AuditLog({self.action}, user={self.user_id}, status={self.status_code})"