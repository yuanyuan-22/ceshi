import time
from django.conf import settings
from django.http import JsonResponse
from django.db import connections
from django.core.cache import cache


def health_check(request):
    checks = {
        "status": "ok",
        "timestamp": time.time(),
        "version": getattr(settings, "SPECTACULAR_SETTINGS", {}).get("VERSION", "unknown"),
        "debug": settings.DEBUG,
    }
    try:
        conn = connections["default"]
        conn.cursor().execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        checks["status"] = "degraded"
    try:
        cache.set("health_check", 1, 1)
        cache.get("health_check")
        checks["cache"] = "ok"
    except Exception as e:
        checks["cache"] = f"error: {e}"
        checks["status"] = "degraded"
    status_code = 200 if checks["status"] == "ok" else 503
    return JsonResponse(checks, status=status_code)
