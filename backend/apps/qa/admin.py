from django.contrib import admin
from .models import QATask


@admin.register(QATask)
class QATaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'question', 'lang', 'status', 'confidence', 'latency_ms', 'created_at']
    list_filter = ['status', 'lang', 'created_at']
    search_fields = ['question', 'answer']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
