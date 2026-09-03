from rest_framework import serializers
from .models import EvalRun, EvalResult


class EvalResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvalResult
        fields = [
            "id", "question", "expected_entity_keys",
            "retrieved_ranks", "top_score", "is_relevant_found",
            "first_relevant_rank", "generated_answer",
            "accuracy_score", "completeness_score", "relevance_score",
            "faithfulness_score", "safety_score",
            "latency_ms",
        ]


class EvalRunSerializer(serializers.ModelSerializer):
    results = EvalResultSerializer(many=True, read_only=True)

    class Meta:
        model = EvalRun
        fields = [
            "id", "eval_type", "eval_mode", "status", "top_k",
            "total_questions", "total_relevant",
            "recall_at_1", "recall_at_3", "recall_at_5",
            "mrr", "ndcg_at_5",
            "recall_at_1_ci", "recall_at_5_ci", "mrr_ci",
            "bm25_recall_at_1", "bm25_recall_at_5", "bm25_mrr", "bm25_ndcg_at_5",
            "avg_accuracy", "avg_completeness", "avg_relevance",
            "avg_faithfulness", "avg_safety",
            "judge_calibration", "judge_model",
            "extra", "created_at", "results",
        ]


class EvalRunListSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvalRun
        fields = [
            "id", "eval_type", "eval_mode", "status", "top_k",
            "total_questions", "total_relevant",
            "recall_at_1", "recall_at_3", "recall_at_5",
            "mrr", "ndcg_at_5",
            "recall_at_1_ci", "recall_at_5_ci", "mrr_ci",
            "bm25_recall_at_1", "bm25_recall_at_5", "bm25_mrr", "bm25_ndcg_at_5",
            "avg_accuracy", "avg_completeness", "avg_relevance",
            "avg_faithfulness", "avg_safety",
            "judge_calibration", "judge_model",
            "created_at",
        ]
