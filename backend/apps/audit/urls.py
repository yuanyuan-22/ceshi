from django.urls import path
from .views import AuditLogListView, HealthCheckView, LatencyTrendsView, ErrorPatternsView

urlpatterns = [
    path("logs/", AuditLogListView.as_view(), name="audit_logs"),
    path("health/", HealthCheckView.as_view(), name="audit_health"),
    path("latency-trends/", LatencyTrendsView.as_view(), name="audit_latency_trends"),
    path("error-patterns/", ErrorPatternsView.as_view(), name="audit_error_patterns"),
]
