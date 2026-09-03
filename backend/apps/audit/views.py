from rest_framework import permissions, generics
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog
from .serializers import AuditLogListSerializer
from .monitoring import get_health_report, get_latency_trends, get_error_patterns


class AuditLogListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AuditLogListSerializer
    queryset = AuditLog.objects.select_related("user").all()
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "latency_ms", "status_code"]
    ordering = ["-created_at"]


class HealthCheckView(APIView):
    """Real-time SLO health check with alert status."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        window = int(request.query_params.get("window_minutes", 60))
        report = get_health_report(window_minutes=window)
        return Response(report)


class LatencyTrendsView(APIView):
    """Latency trend data for dashboard time-series charts."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get("days", 7))
        bucket = int(request.query_params.get("bucket_minutes", 60))
        trends = get_latency_trends(days=days, bucket_minutes=bucket)
        return Response(trends)


class ErrorPatternsView(APIView):
    """Error pattern analysis for proactive issue detection."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        days = int(request.query_params.get("days", 7))
        patterns = get_error_patterns(days=days)
        return Response(patterns)
