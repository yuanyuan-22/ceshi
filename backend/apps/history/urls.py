# backend/apps/history/urls.py
from django.urls import path,include
from .views import TranslationHistoryView, QAHistoryView

urlpatterns = [
    path("translations/", TranslationHistoryView.as_view(), name="history_translations"),
    path("qas/", QAHistoryView.as_view(), name="history_qas"),
]