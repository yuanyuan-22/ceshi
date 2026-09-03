from django.urls import path
from .views import (
    FeedbackCreateView, FeedbackListView, FeedbackMineView,
    FeedbackResolveView, FeedbackAnalyticsView,
    FeedbackExportView, WeeklyBadCaseReportView,
)

urlpatterns = [
    path("", FeedbackCreateView.as_view(), name="feedback_create"),
    path("list/", FeedbackListView.as_view(), name="feedback_list"),
    path("mine/", FeedbackMineView.as_view(), name="feedback_mine"),
    path("<int:pk>/resolve/", FeedbackResolveView.as_view(), name="feedback_resolve"),
    path("analytics/", FeedbackAnalyticsView.as_view(), name="feedback_analytics"),
    path("export/", FeedbackExportView.as_view(), name="feedback_export"),
    path("bad-cases/", WeeklyBadCaseReportView.as_view(), name="feedback_bad_cases"),
]
