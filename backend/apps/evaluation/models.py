from django.conf import settings
from django.db import models


class EvalRun(models.Model):
    EVAL_TYPE_CHOICES = [
        ("rag_retrieval", "RAG Retrieval"),
        ("answer_quality", "Answer Quality (LLM-as-Judge)"),
        ("full_pipeline", "Full Pipeline"),
    ]

    EVAL_MODE_CHOICES = [
        ("hard", "Hard (symptom-based)"),
        ("smoke", "Smoke (name-based, internal)"),
        ("both", "Both modes"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="eval_runs",
    )
    eval_type = models.CharField(max_length=32, choices=EVAL_TYPE_CHOICES)
    eval_mode = models.CharField(max_length=16, blank=True, default="hard")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    top_k = models.IntegerField(default=5)

    total_questions = models.IntegerField(default=0)
    total_relevant = models.IntegerField(default=0)
    recall_at_1 = models.FloatField(default=0.0)
    recall_at_3 = models.FloatField(default=0.0)
    recall_at_5 = models.FloatField(default=0.0)
    mrr = models.FloatField(default=0.0)
    ndcg_at_5 = models.FloatField(default=0.0)
    avg_accuracy = models.FloatField(null=True, blank=True)
    avg_completeness = models.FloatField(null=True, blank=True)
    avg_relevance = models.FloatField(null=True, blank=True)
    avg_faithfulness = models.FloatField(null=True, blank=True)
    avg_safety = models.FloatField(null=True, blank=True)

    recall_at_1_ci = models.JSONField(blank=True, default=dict)
    recall_at_5_ci = models.JSONField(blank=True, default=dict)
    mrr_ci = models.JSONField(blank=True, default=dict)

    bm25_recall_at_1 = models.FloatField(null=True, blank=True)
    bm25_recall_at_5 = models.FloatField(null=True, blank=True)
    bm25_mrr = models.FloatField(null=True, blank=True)
    bm25_ndcg_at_5 = models.FloatField(null=True, blank=True)

    judge_calibration = models.JSONField(blank=True, default=dict)
    judge_model = models.CharField(max_length=128, blank=True, default="")

    extra = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["eval_type", "created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["eval_mode"]),
        ]

    def __str__(self):
        return f"EvalRun({self.eval_type}, {self.eval_mode}, {self.status}, {self.created_at:%Y-%m-%d %H:%M})"


class EvalResult(models.Model):
    run = models.ForeignKey(EvalRun, on_delete=models.CASCADE, related_name="results")
    question = models.TextField()
    expected_entity_keys = models.JSONField(blank=True, default=list)

    retrieved_ranks = models.JSONField(blank=True, default=list)
    top_score = models.FloatField(default=0.0)
    is_relevant_found = models.BooleanField(default=False)
    first_relevant_rank = models.IntegerField(null=True, blank=True)

    generated_answer = models.TextField(blank=True, default="")
    accuracy_score = models.FloatField(null=True, blank=True)
    completeness_score = models.FloatField(null=True, blank=True)
    relevance_score = models.FloatField(null=True, blank=True)
    faithfulness_score = models.FloatField(null=True, blank=True)
    safety_score = models.FloatField(null=True, blank=True)
    judge_raw = models.JSONField(blank=True, default=dict)

    latency_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["run", "id"]
        indexes = [
            models.Index(fields=["run", "is_relevant_found"]),
        ]
