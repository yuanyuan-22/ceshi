import time
import uuid
from django.utils.deprecation import MiddlewareMixin


class AuditRequestMiddleware(MiddlewareMixin):
    """
    - 给每个请求加 request_id
    - 记录开始时间，方便你在各业务 view 里写 audit 时带上 latency
    """
    def process_request(self, request):
        request.request_start_time = time.time()
        request.request_id = request.META.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex[:16]

    def process_response(self, request, response):
        try:
            response["X-Request-Id"] = getattr(request, "request_id", "")
        except Exception:
            pass
        return response