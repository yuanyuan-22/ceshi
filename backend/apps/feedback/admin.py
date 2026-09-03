# backend/apps/feedback/admin.py
from django.contrib import admin
from .models import Feedback

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "scene", "rating", "task_type", "task_id", "user", "created_at")
    list_filter = ("scene", "rating", "task_type")
    search_fields = ("task_id", "comment", "corrected_translation", "user__username")
    ordering = ("-created_at",)
