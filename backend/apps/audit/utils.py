import time
import uuid
from django.utils.timezone import now
from .models import AuditLog
from typing import Optional, Dict, Any

def _get_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def ensure_request_id(request):
    rid = request.META.get("HTTP_X_REQUEST_ID") or getattr(request, "request_id", "")
    if not rid:
        rid = uuid.uuid4().hex[:16]
    request.request_id = rid
    return rid


def write_audit(
    *,
    request,
    action: str,
    status_code: Optional[int] = None,
    user=None,
    latency_ms: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    try:
        rid = ensure_request_id(request)
        ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:512]
        ip = _get_ip(request)
        if user is None:
            u = getattr(request, "user", None)
            if u is not None and getattr(u, "is_authenticated", False):
                user = u
        AuditLog.objects.create(
            user=user if (user and getattr(user, "is_authenticated", True)) else None,
            action=action,
            method=getattr(request, "method", "") or "",
            path=getattr(request, "path", "") or "",
            status_code=status_code,
            ip=ip,
            user_agent=ua,
            request_id=rid,
            latency_ms=latency_ms,
            extra=extra or {},
        )
    except Exception:
        # 审计日志不能影响业务主流程
        pass