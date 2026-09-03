import time

from rest_framework import permissions, generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from audit.utils import write_audit

from .models import Feedback
from .serializers import FeedbackCreateSerializer, FeedbackListSerializer, FeedbackResolveSerializer
from .services import get_feedback_analytics, export_feedback_for_finetuning, get_weekly_bad_case_report


class FeedbackCreateView(generics.CreateAPIView):
    serializer_class = FeedbackCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        obj = serializer.save(user=self.request.user)

        latency_ms = None
        if hasattr(self.request, "request_start_time"):
            latency_ms = int((time.time() - self.request.request_start_time) * 1000)

        write_audit(
            request=self.request,
            action="feedback.create",
            status_code=201,
            latency_ms=latency_ms,
            extra={
                "scene": obj.scene,
                "task_type": obj.task_type,
                "task_id": obj.task_id,
                "rating": obj.rating,
                "entity_keys": obj.related_entity_keys,
            },
        )


class FeedbackListView(generics.ListAPIView):
    serializer_class = FeedbackListSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Feedback.objects.select_related("user").all()
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["scene", "task_type", "task_id", "rating", "resolution", "user__id"]
    ordering_fields = ["created_at", "rating"]
    ordering = ["-created_at"]


class _StdLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 10
    max_limit = 100


class FeedbackMineView(generics.ListAPIView):
    serializer_class = FeedbackListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = _StdLimitOffsetPagination

    def get_queryset(self):
        return Feedback.objects.select_related("user").filter(
            user=self.request.user
        ).order_by("-created_at")


class FeedbackResolveView(APIView):
    """Admin resolves a pending feedback item (accept/reject)."""
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            fb = Feedback.objects.get(pk=pk)
        except Feedback.DoesNotExist:
            return Response({"error": "Feedback not found"}, status=404)

        serializer = FeedbackResolveSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        fb.resolve(
            resolution=serializer.validated_data["resolution"],
            resolved_by=request.user,
            note=serializer.validated_data.get("note", ""),
        )

        write_audit(
            request=request,
            action="feedback.resolve",
            status_code=200,
            extra={
                "feedback_id": fb.id,
                "resolution": fb.resolution,
            },
        )

        return Response(FeedbackListSerializer(fb).data)


class FeedbackAnalyticsView(APIView):
    """Dashboard analytics for feedback data."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        scene = request.query_params.get("scene", "qa")
        days = int(request.query_params.get("days", 30))
        result = get_feedback_analytics(scene=scene, days=days)
        return Response(result)


class FeedbackExportView(APIView):
    """Export feedback data for fine-tuning (RLHF data flywheel)."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        days = int(request.query_params.get("days", 90))
        min_rating = int(request.query_params.get("min_rating", 1))
        corrections_only = request.query_params.get("corrections_only", "false").lower() == "true"
        max_samples = int(request.query_params.get("max_samples", 100))

        samples = export_feedback_for_finetuning(
            scene="qa", days=days, min_rating=min_rating,
            include_corrections_only=corrections_only, max_samples=max_samples,
        )

        return Response({
            "total": len(samples),
            "samples": samples,
            "format_note": "Each sample with 'preference_pair' can be used for DPO/RLHF training. "
                          "Samples with 'human_correction' can be used for SFT.",
        })


class WeeklyBadCaseReportView(APIView):
    """Weekly report of worst-performing cases."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        report = get_weekly_bad_case_report()
        return Response(report)
