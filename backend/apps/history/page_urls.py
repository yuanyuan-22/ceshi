from django.urls import path
from .page_views import HomeView, TranslatePageView, QAPageView, HistoryPageView
from . import page_views
from accounts.page_views import profile_page
from backend.apps.appointments.page_views import AppointmentPageView
from backend.apps.translation.page_views import MedicalTextAnalysisPageView
from backend.apps.feedback.page_views import SystemFeedbackPageView

urlpatterns = [
    path("", page_views.login_page, name="root"),
    path("login/", page_views.login_page, name="login"),
    path("home/", page_views.home_page, name="home"),
    path("register/", page_views.register_page, name="register"),
    path("translate/", TranslatePageView.as_view(), name="page_translate"),
    path("qa/", QAPageView.as_view(), name="page_qa"),
    path("medical-text-analysis/", MedicalTextAnalysisPageView.as_view(), name="page_medical_text_analysis"),
    path("feedback/", SystemFeedbackPageView.as_view(), name="page_system_feedback"),
    path("history/", HistoryPageView.as_view(), name="page_history"),
    path("appointments/", AppointmentPageView.as_view(), name="page_appointments"),
    path("profile/", profile_page, name="profile"),
]
