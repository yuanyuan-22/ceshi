# backend/apps/history/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from translation.models import TranslationTask
from qa.models import QATask


def _safe_int(value, default, min_v=None, max_v=None):
    try:
        x = int(value)
    except (TypeError, ValueError):
        x = default
    if min_v is not None:
        x = max(min_v, x)
    if max_v is not None:
        x = min(max_v, x)
    return x


class TranslationHistoryView(APIView):
    """
    GET /api/history/translations/?limit=20&offset=0
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = _safe_int(request.query_params.get("limit"), 10, 1, 100)
        offset = _safe_int(request.query_params.get("offset"), 0, 0, 100000)

        qs = (
            TranslationTask.objects
            .filter(user=request.user)
            .order_by("-id")
        )

        total = qs.count()
        items = qs[offset: offset + limit]

        data = []
        for x in items:
            data.append({
                "id": x.id,
                "src_lang": x.src_lang,
                "tgt_lang": x.tgt_lang,
                "domain": x.domain or "",
                "input_text": x.input_text,
                "base_translation": x.base_translation or "",
                "lora_translation": x.lora_translation or "",
                "output_text": x.output_text or "",
                "terms_json": x.terms_json or [],
                "latency_ms": x.latency_ms,
                "status": x.status,
                "created_at": x.created_at.isoformat() if x.created_at else None,
            })

        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "results": data,
        }, status=status.HTTP_200_OK)


class QAHistoryView(APIView):
    """
    GET /api/history/qas/?limit=20&offset=0
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = _safe_int(request.query_params.get("limit"), 10, 1, 100)
        offset = _safe_int(request.query_params.get("offset"), 0, 0, 100000)

        qs = (
            QATask.objects
            .filter(user=request.user)
            .order_by("-id")
        )

        total = qs.count()
        items = qs[offset: offset + limit]

        data = []
        for x in items:
            data.append({
                "id": x.id,
                "question": x.question,
                "lang": x.lang,
                "answer": x.answer,
                "confidence": float(x.confidence) if x.confidence is not None else None,
                "sources_json": x.sources_json or [],
                "latency_ms": x.latency_ms,
                "status": x.status,
                "created_at": getattr(x, "created_at", None),
            })

        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "results": data,
        }, status=status.HTTP_200_OK)