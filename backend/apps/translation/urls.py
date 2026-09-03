from django.urls import path

from .analysis_views import MedicalTextAnalysisView
from .views import TranslateView

urlpatterns = [
    path("", TranslateView.as_view(), name="translate"),
    path("analyze/", MedicalTextAnalysisView.as_view(), name="medical_text_analyze"),
]
