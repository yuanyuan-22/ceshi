from django.contrib import admin
from .models import EvalRun, EvalResult


@admin.register(EvalRun)
class EvalRunAdmin(admin.ModelAdmin):
    list_display = ["id", "eval_type", "status", "total_questions", "recall_at_5", "mrr", "avg_accuracy", "created_at"]
    list_filter = ["eval_type", "status"]
    readonly_fields = [
        "recall_at_1", "recall_at_3", "recall_at_5", "mrr", "ndcg_at_5",
        "avg_accuracy", "avg_completeness", "avg_relevance",
    ]


@admin.register(EvalResult)
class EvalResultAdmin(admin.ModelAdmin):
    list_display = ["id", "run", "question", "is_relevant_found", "accuracy_score", "created_at_short"]
    list_filter = ["is_relevant_found"]

    def created_at_short(self, obj):
        return obj.run.created_at.strftime("%Y-%m-%d %H:%M")
    created_at_short.short_description = "Run Time"
