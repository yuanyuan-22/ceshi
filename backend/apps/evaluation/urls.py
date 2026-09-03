from django.urls import path
from .views import (
    EvalRunListView,
    EvalRunDetailView,
    TriggerRAGEvalView,
    TriggerAnswerQualityEvalView,
    JudgeCalibrationView,
    QualityDashboardView,
    judge_single_answer,
)

urlpatterns = [
    path("runs/", EvalRunListView.as_view(), name="eval_runs"),
    path("runs/<int:pk>/", EvalRunDetailView.as_view(), name="eval_run_detail"),
    path("trigger/rag/", TriggerRAGEvalView.as_view(), name="eval_trigger_rag"),
    path("trigger/answer_quality/", TriggerAnswerQualityEvalView.as_view(), name="eval_trigger_answer_quality"),
    path("calibrate/judge/", JudgeCalibrationView.as_view(), name="eval_calibrate_judge"),
    path("dashboard/", QualityDashboardView.as_view(), name="eval_dashboard"),
    path("judge/", judge_single_answer, name="eval_judge_single"),
]
