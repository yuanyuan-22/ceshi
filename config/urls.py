from django.contrib import admin
from django.urls import path, include
from django.templatetags.static import static
from django.views.generic import RedirectView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from backend.core.views import health_check

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    path("favicon.ico", RedirectView.as_view(url=static("favicon.svg"), permanent=False)),

    # Health
    path("api/health/", health_check, name="health_check"),

    # API Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # Auth (JWT)
    path("api/auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/", include("accounts.urls")),

    # APIs
    path("api/translate/", include("translation.urls")),
    path("api/qa/", include("qa.urls")),
    path("api/history/", include("history.urls")),
    path("api/appointments/", include("backend.apps.appointments.urls")),
    path("kb/", include("backend.apps.kb.urls")),
    path("api/kb/", include("backend.apps.kb.urls")),

    # Pages
    path("", include("history.page_urls")),
    path("api/feedback/", include("feedback.urls")),
    path("api/audit/", include("audit.urls")),
    path("api/eval/", include("evaluation.urls")),
]

