# Generated migration for evaluation app
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EvalRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("eval_type", models.CharField(choices=[("rag_retrieval", "RAG Retrieval"), ("answer_quality", "Answer Quality (LLM-as-Judge)"), ("full_pipeline", "Full Pipeline")], max_length=32)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")], default="pending", max_length=16)),
                ("top_k", models.IntegerField(default=5)),
                ("total_questions", models.IntegerField(default=0)),
                ("total_relevant", models.IntegerField(default=0)),
                ("recall_at_1", models.FloatField(default=0.0)),
                ("recall_at_3", models.FloatField(default=0.0)),
                ("recall_at_5", models.FloatField(default=0.0)),
                ("mrr", models.FloatField(default=0.0)),
                ("ndcg_at_5", models.FloatField(default=0.0)),
                ("avg_accuracy", models.FloatField(blank=True, null=True)),
                ("avg_completeness", models.FloatField(blank=True, null=True)),
                ("avg_relevance", models.FloatField(blank=True, null=True)),
                ("extra", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="eval_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["eval_type", "created_at"], name="eval_evalrun_type_created_idx"),
                    models.Index(fields=["status"], name="eval_evalrun_status_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="EvalResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.TextField()),
                ("expected_entity_keys", models.JSONField(blank=True, default=list)),
                ("retrieved_ranks", models.JSONField(blank=True, default=list)),
                ("top_score", models.FloatField(default=0.0)),
                ("is_relevant_found", models.BooleanField(default=False)),
                ("first_relevant_rank", models.IntegerField(blank=True, null=True)),
                ("generated_answer", models.TextField(blank=True, default="")),
                ("accuracy_score", models.FloatField(blank=True, null=True)),
                ("completeness_score", models.FloatField(blank=True, null=True)),
                ("relevance_score", models.FloatField(blank=True, null=True)),
                ("judge_raw", models.JSONField(blank=True, default=dict)),
                ("latency_ms", models.IntegerField(blank=True, null=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="results", to="evaluation.evalrun")),
            ],
            options={
                "ordering": ["run", "id"],
                "indexes": [
                    models.Index(fields=["run", "is_relevant_found"], name="eval_evalresult_run_found_idx"),
                ],
            },
        ),
    ]
