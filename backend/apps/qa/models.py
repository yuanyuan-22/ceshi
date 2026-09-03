from django.conf import settings
from django.db import models

class QATask(models.Model):
    STATUS_CHOICES = [
        ("SUCCESS", "SUCCESS"),
        ("FAIL", "FAIL"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="qa_tasks"
    )
    question = models.TextField()
    lang = models.CharField(max_length=16, default="zh")

    answer = models.TextField(blank=True, default="")
    confidence = models.FloatField(default=0.0)
    sources_json = models.JSONField(blank=True, default=list)

    auto_accuracy = models.FloatField(null=True, blank=True)
    auto_completeness = models.FloatField(null=True, blank=True)
    auto_relevance = models.FloatField(null=True, blank=True)
    auto_judge_raw = models.JSONField(blank=True, default=dict)

    latency_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="SUCCESS")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]