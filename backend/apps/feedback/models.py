from django.conf import settings
from django.db import models
from django.utils import timezone


class Feedback(models.Model):
    class Scene(models.TextChoices):
        TRANSLATION = "translation", "Translation"
        QA = "qa", "QA"
        SYSTEM = "system", "System"

    class Resolution(models.TextChoices):
        PENDING = "pending", "Pending Review"
        ACCEPTED = "accepted", "Accepted — KB Updated"
        REJECTED = "rejected", "Rejected — Not Actionable"
        DEFERRED = "deferred", "Deferred — Future Consideration"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedbacks"
    )
    scene = models.CharField(max_length=32, choices=Scene.choices)
    task_type = models.CharField(max_length=64, blank=True, default="")
    task_id = models.CharField(max_length=64, blank=True, default="")

    rating = models.SmallIntegerField()
    rating_accuracy = models.SmallIntegerField(null=True, blank=True)
    rating_clarity = models.SmallIntegerField(null=True, blank=True)
    rating_completeness = models.SmallIntegerField(null=True, blank=True)
    rating_safety = models.SmallIntegerField(null=True, blank=True)

    comment = models.TextField(blank=True, default="")
    corrected_answer = models.TextField(blank=True, default="")
    corrected_translation = models.TextField(blank=True, default="")

    related_entity_keys = models.JSONField(blank=True, default=list)

    resolution = models.CharField(
        max_length=16, choices=Resolution.choices, default=Resolution.PENDING
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="resolved_feedbacks"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default="")

    extra = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["scene", "created_at"]),
            models.Index(fields=["task_type", "task_id"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["resolution", "scene"]),
            models.Index(fields=["scene", "rating"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Feedback({self.scene}, rating={self.rating}, resolution={self.resolution})"

    def is_negative(self) -> bool:
        return self.rating <= -1 or (self.rating_accuracy is not None and self.rating_accuracy <= 2)

    def is_positive(self) -> bool:
        return self.rating >= 1

    def has_correction(self) -> bool:
        return bool((self.corrected_answer or self.corrected_translation or "").strip())

    def resolve(self, resolution: str, resolved_by, note: str = ""):
        self.resolution = resolution
        self.resolved_by = resolved_by
        self.resolved_at = timezone.now()
        self.resolution_note = note
        self.save(update_fields=["resolution", "resolved_by", "resolved_at", "resolution_note"])
