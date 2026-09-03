import time

from rest_framework import permissions, generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.utils import write_audit

from .models import EvalRun, EvalResult
from .serializers import EvalRunSerializer, EvalRunListSerializer
from .services import (
    evaluate_rag_retrieval,
    evaluate_answer_quality_full,
    calibrate_judge,
    get_qa_quality_stats,
    judge_answer_quality,
)


class EvalRunListView(generics.ListAPIView):
    serializer_class = EvalRunListSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = EvalRun.objects.all()
    ordering = ["-created_at"]


class EvalRunDetailView(generics.RetrieveAPIView):
    serializer_class = EvalRunSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = EvalRun.objects.prefetch_related("results")


class TriggerRAGEvalView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        top_k = int(request.data.get("top_k", 5))
        max_questions = int(request.data.get("max_questions", 100))
        eval_mode = request.data.get("eval_mode", "hard")
        include_baseline = request.data.get("include_baseline", True)

        run = EvalRun.objects.create(
            user=request.user,
            eval_type="rag_retrieval",
            eval_mode=eval_mode,
            status="running",
            top_k=top_k,
            total_questions=0,
        )

        try:
            t0 = time.time()
            result = evaluate_rag_retrieval(
                top_k=top_k,
                max_questions=max_questions,
                eval_mode=eval_mode,
                include_baseline=include_baseline,
            )
            latency_ms = int((time.time() - t0) * 1000)

            if result.get("error"):
                run.status = "failed"
                run.extra = {"error": result["error"]}
                run.save()
                return Response({"error": result["error"]}, status=500)

            primary = result.get("hard") or result.get("smoke") or {}
            baseline = result.get("hard_bm25_baseline") or {}

            run.total_questions = primary.get("total_questions", 0)
            run.total_relevant = primary.get("total_relevant_found", 0)
            run.recall_at_1 = primary.get("recall_at_1", 0.0)
            run.recall_at_3 = primary.get("recall_at_3", 0.0)
            run.recall_at_5 = primary.get("recall_at_5", 0.0)
            run.mrr = primary.get("mrr", 0.0)
            run.ndcg_at_5 = primary.get("ndcg_at_5", 0.0)
            run.recall_at_1_ci = primary.get("recall_at_1_ci") or {}
            run.recall_at_5_ci = primary.get("recall_at_5_ci") or {}
            run.mrr_ci = primary.get("mrr_ci") or {}

            if baseline:
                run.bm25_recall_at_1 = baseline.get("recall_at_1")
                run.bm25_recall_at_5 = baseline.get("recall_at_5")
                run.bm25_mrr = baseline.get("mrr")
                run.bm25_ndcg_at_5 = baseline.get("ndcg_at_5")

            run.extra = {
                "latency_ms": latency_ms,
                "top_k": top_k,
                "eval_mode": eval_mode,
                "by_category": primary.get("by_category", {}),
                "bm25_baseline": baseline.get("recall_at_5") if baseline else None,
                "raw_result": result,
            }
            run.status = "completed"
            run.save()

            per_questions = primary.get("per_question", [])
            for pq in per_questions:
                EvalResult.objects.create(
                    run=run,
                    question=pq["question"],
                    expected_entity_keys=pq["expected_entity_keys"],
                    retrieved_ranks=pq.get("ranks", []),
                    top_score=pq.get("top_score", 0.0),
                    is_relevant_found=pq.get("is_relevant_found", False),
                    first_relevant_rank=pq.get("first_relevant_rank"),
                )

            write_audit(
                request=request,
                action="eval.rag_retrieval.run",
                status_code=200,
                latency_ms=latency_ms,
                extra={"run_id": run.id, "eval_type": "rag_retrieval", "eval_mode": eval_mode},
            )

            return Response({"run": EvalRunSerializer(run).data, "summary": result}, status=status.HTTP_201_CREATED)

        except Exception as e:
            run.status = "failed"
            run.extra = {"error": str(e)}
            run.save()
            return Response({"error": str(e)}, status=500)


class TriggerAnswerQualityEvalView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        max_questions = int(request.data.get("max_questions", 20))
        judge_model = request.data.get("judge_model", "Qwen/Qwen2.5-7B-Instruct")

        run = EvalRun.objects.create(
            user=request.user,
            eval_type="answer_quality",
            status="running",
            top_k=5,
            total_questions=0,
            judge_model=judge_model,
        )

        try:
            t0 = time.time()
            result = evaluate_answer_quality_full(max_questions=max_questions, judge_model=judge_model)
            latency_ms = int((time.time() - t0) * 1000)

            run.total_questions = result["total_questions"]
            run.avg_accuracy = result.get("avg_accuracy", 0)
            run.avg_completeness = result.get("avg_completeness", 0)
            run.avg_relevance = result.get("avg_relevance", 0)
            run.avg_faithfulness = result.get("avg_faithfulness", 0)
            run.avg_safety = result.get("avg_safety", 0)
            run.extra = {"latency_ms": latency_ms}
            run.status = "completed"
            run.save()

            for pq in result.get("per_question", []):
                EvalResult.objects.create(
                    run=run,
                    question=pq["question"],
                    expected_entity_keys=pq.get("expected_entity_keys", []),
                    is_relevant_found=pq.get("is_relevant_found", False),
                    generated_answer=pq.get("answer", ""),
                    accuracy_score=pq.get("accuracy"),
                    completeness_score=pq.get("completeness"),
                    relevance_score=pq.get("relevance"),
                    faithfulness_score=pq.get("faithfulness"),
                    safety_score=pq.get("safety"),
                    judge_raw=pq.get("judge_raw", {}),
                )

            write_audit(
                request=request,
                action="eval.answer_quality.run",
                status_code=200,
                latency_ms=latency_ms,
                extra={"run_id": run.id, "judge_model": judge_model},
            )

            return Response(EvalRunSerializer(run).data, status=status.HTTP_201_CREATED)

        except Exception as e:
            run.status = "failed"
            run.extra = {"error": str(e)}
            run.save()
            return Response({"error": str(e)}, status=500)


class QualityDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        stats = get_qa_quality_stats()
        return Response(stats)


@api_view(["POST"])
@permission_classes([permissions.IsAdminUser])
def judge_single_answer(request):
    question = (request.data.get("question") or "").strip()
    answer = (request.data.get("answer") or "").strip()
    context = (request.data.get("context") or "").strip()
    judge_model = request.data.get("judge_model", "Qwen/Qwen2.5-7B-Instruct")

    if not question or not answer:
        return Response({"error": "question and answer are required"}, status=400)

    result = judge_answer_quality(question, answer, context, judge_model=judge_model)
    return Response(result)


class JudgeCalibrationView(APIView):
    """Calibrate LLM judge against human-annotated gold set."""
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        judge_model = request.data.get("judge_model", "Qwen/Qwen2.5-7B-Instruct")
        max_samples = int(request.data.get("max_samples", 20))

        t0 = time.time()
        result = calibrate_judge(judge_model=judge_model, max_samples=max_samples)
        latency_ms = int((time.time() - t0) * 1000)

        run = EvalRun.objects.create(
            user=request.user,
            eval_type="answer_quality",
            eval_mode="judge_calibration",
            status="completed",
            total_questions=result.get("calibrated_samples", 0),
            judge_model=judge_model,
            judge_calibration=result.get("correlation", {}),
            extra={"latency_ms": latency_ms, "verdict": result.get("verdict", "")},
        )

        write_audit(
            request=request,
            action="eval.judge_calibration.run",
            status_code=200,
            latency_ms=latency_ms,
            extra={"run_id": run.id, "judge_model": judge_model},
        )

        return Response({
            "run": EvalRunSerializer(run).data,
            "calibration": result,
        }, status=status.HTTP_201_CREATED)
