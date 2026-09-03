from __future__ import annotations

import os

from django.db import DatabaseError
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CandidateEntity, KBEntity, RawKBUpload
from .scripts.build_multilang import build_multilang
from .scripts.generate_training_data import main as generate_training_data_main
from .services import (
    approve_candidate_entity,
    extract_candidate_payloads,
    reject_candidate_entity,
    replace_candidate_entity,
    replace_kb_entity,
    upsert_kb_entity,
)
from .translator import translate_kb_entity
from .utils import UploadedFileReadError, extract_text_from_uploaded


def _staff_only(request) -> Response | None:
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_staff:
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
    return None


def _auth_only(request) -> Response | None:
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
    return None


def _content_preview(content: str, limit: int = 300) -> str:
    content = (content or "").strip()
    if len(content) <= limit:
        return content
    return f"{content[:limit]}..."


def _upload_source_name(raw: RawKBUpload) -> str:
    return raw.file.name if raw.file else f"upload_{raw.id}"


def _serialize_entity(entity: KBEntity) -> dict:
    term_cards = [
        {
            "lang": card.lang,
            "term": card.term,
            "type": card.type,
            "explain": card.explain_text,
        }
        for card in entity.term_cards.all().order_by("lang")
    ]
    return {
        "id": entity.id,
        "entity_key": entity.entity_key,
        "canonical_key": entity.canonical_key,
        "category": entity.category,
        "source": entity.source,
        "langs": entity.langs or {},
        "term_cards": term_cards,
        "created_at": entity.created_at.isoformat() if entity.created_at else "",
        "updated_at": entity.updated_at.isoformat() if entity.updated_at else "",
    }


def _candidate_label(candidate: CandidateEntity) -> str:
    payload = candidate.payload or {}
    langs = payload.get("langs") or {}
    for lang in ("zh", "en", "ja", "fr", "de"):
        block = langs.get(lang) or {}
        term = (block.get("term") or "").strip()
        if term:
            return term
    return (payload.get("canonical_key") or payload.get("entity_key") or f"candidate_{candidate.id}").strip()


def _serialize_candidate(candidate: CandidateEntity, *, include_payload: bool = True) -> dict:
    payload = candidate.payload or {}
    approved = candidate.approved_entity
    return {
        "id": candidate.id,
        "raw_upload_id": candidate.raw_upload_id,
        "status": candidate.status,
        "confidence": candidate.confidence,
        "extraction_method": candidate.extraction_method,
        "label": _candidate_label(candidate),
        "payload": payload if include_payload else {},
        "evidence_text": candidate.evidence_text,
        "review_notes": candidate.review_notes,
        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else "",
        "reviewed_by": candidate.reviewed_by.username if candidate.reviewed_by else "",
        "approved_entity": (
            {
                "id": approved.id,
                "entity_key": approved.entity_key,
                "canonical_key": approved.canonical_key,
            }
            if approved
            else None
        ),
    }


def _serialize_upload(raw: RawKBUpload, *, include_content: bool = False) -> dict:
    source_name = _upload_source_name(raw)
    related_entities = list(
        KBEntity.objects.filter(source=source_name)
        .only("id", "entity_key", "canonical_key", "category", "updated_at")
        .order_by("-id")[:50]
    )
    related_candidates = list(
        raw.candidates.all()
        .select_related("approved_entity", "reviewed_by")
        .order_by("-id")[:50]
    )
    candidate_statuses = [candidate.status for candidate in related_candidates]
    return {
        "id": raw.id,
        "status": raw.status,
        "file_type": raw.file_type,
        "uploaded_by": raw.uploaded_by.username if raw.uploaded_by else "",
        "created_at": raw.created_at.isoformat() if raw.created_at else "",
        "updated_at": raw.updated_at.isoformat() if raw.updated_at else "",
        "file_name": os.path.basename(raw.file.name) if raw.file else "",
        "file_path": raw.file.path if raw.file else "",
        "source_name": source_name,
        "content_preview": _content_preview(raw.content),
        "content": raw.content if include_content else "",
        "candidate_count": len(related_candidates),
        "pending_candidate_count": sum(1 for value in candidate_statuses if value == "PENDING"),
        "approved_candidate_count": sum(1 for value in candidate_statuses if value == "APPROVED"),
        "related_entities": [
            {
                "id": entity.id,
                "entity_key": entity.entity_key,
                "canonical_key": entity.canonical_key,
                "category": entity.category,
                "updated_at": entity.updated_at.isoformat() if entity.updated_at else "",
            }
            for entity in related_entities
        ],
        "related_candidates": [_serialize_candidate(candidate, include_payload=False) for candidate in related_candidates],
    }


class KBUploadView(APIView):
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        denied = _auth_only(request)
        if denied is not None:
            return denied

        uploaded = request.FILES.get("file")
        text_content = (request.data.get("text") or "").strip()

        if uploaded:
            file_type = os.path.splitext(uploaded.name)[1].lower().replace(".", "") or "other"
            if file_type not in {"txt", "docx"}:
                file_type = "other"
            raw = RawKBUpload.objects.create(
                file=uploaded,
                file_type=file_type,
                uploaded_by=request.user,
                status="NEW",
            )
            try:
                extracted = extract_text_from_uploaded(raw.file.path)
            except UploadedFileReadError as exc:
                return Response(
                    {
                        "error": "file_extract_failed",
                        "detail": str(exc),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raw.content = extracted
            raw.save(update_fields=["content", "updated_at"])
            return Response(
                {
                    "upload_id": raw.id,
                    "file_type": raw.file_type,
                    "content_length": len(extracted or ""),
                    "content_preview": _content_preview(extracted),
                }
            )

        if text_content:
            raw = RawKBUpload.objects.create(
                content=text_content,
                file_type="txt",
                uploaded_by=request.user,
                status="NEW",
            )
            return Response(
                {
                    "upload_id": raw.id,
                    "file_type": raw.file_type,
                    "content_length": len(text_content),
                    "content_preview": _content_preview(text_content),
                }
            )

        return Response({"error": "no content"}, status=status.HTTP_400_BAD_REQUEST)


class KBProcessView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def post(self, request, upload_id, *args, **kwargs):
        denied = _staff_only(request)
        if denied is not None:
            return denied

        raw = get_object_or_404(RawKBUpload, id=upload_id)
        content = (raw.content or "").strip()
        if not content:
            return Response({"error": "empty upload content"}, status=status.HTTP_400_BAD_REQUEST)

        candidate_rows = extract_candidate_payloads(
            content=content,
            source_name=_upload_source_name(raw),
            default_term=(request.data.get("zh_term") or "").strip(),
            default_category=(request.data.get("category") or "unknown").strip(),
            default_canonical_key=(request.data.get("canonical_key") or "").strip(),
        )
        if not candidate_rows:
            return Response({"error": "no candidate entities extracted"}, status=status.HTTP_400_BAD_REQUEST)

        CandidateEntity.objects.filter(raw_upload=raw, status__in=["PENDING", "REJECTED"]).delete()
        created_candidates = []
        for row in candidate_rows:
            candidate = CandidateEntity.objects.create(
                raw_upload=raw,
                payload=row.get("payload") or {},
                extraction_method=(row.get("extraction_method") or "").strip(),
                confidence=float(row.get("confidence") or 0.0),
                evidence_text=(row.get("evidence_text") or "").strip(),
            )
            created_candidates.append(candidate)

        raw.status = "PARSED"
        raw.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "upload_id": raw.id,
                "candidate_count": len(created_candidates),
                "candidates": [_serialize_candidate(candidate) for candidate in created_candidates],
            }
        )


class KBListView(APIView):
    def get(self, request, *args, **kwargs):
        denied = _auth_only(request)
        if denied is not None:
            return denied

        try:
            # Avoid MySQL filesort on large JSON rows by using the PK index first.
            items = list(
                KBEntity.objects.all()
                .only("id", "entity_key", "canonical_key", "category", "source", "langs", "updated_at")
                .order_by("-id")[:300]
            )
        except DatabaseError as exc:
            return Response(
                {
                    "error": "kb_entities_query_failed",
                    "detail": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        items.sort(key=lambda item: item.updated_at, reverse=True)
        items = items[:100]
        data = []
        for item in items:
            langs = item.langs or {}
            zh_term = ""
            if isinstance(langs.get("zh"), dict):
                zh_term = langs["zh"].get("term", "")
            data.append(
                {
                    "id": item.id,
                    "entity_key": item.entity_key,
                    "canonical_key": item.canonical_key,
                    "category": item.category,
                    "source": item.source,
                    "zh_term": zh_term,
                    "langs_present": sorted([lang for lang in langs.keys() if lang]),
                    "updated_at": item.updated_at.isoformat() if item.updated_at else "",
                }
            )
        return Response(data)


class KBEntityDetailView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def get(self, request, entity_id, *args, **kwargs):
        denied = _auth_only(request)
        if denied is not None:
            return denied

        entity = get_object_or_404(KBEntity, id=entity_id)
        return Response(_serialize_entity(entity))

    def patch(self, request, entity_id, *args, **kwargs):
        denied = _staff_only(request)
        if denied is not None:
            return denied

        entity = get_object_or_404(KBEntity, id=entity_id)
        payload = request.data if isinstance(request.data, dict) else {}
        entity_key = (payload.get("entity_key") or entity.entity_key or "").strip()
        if not entity_key:
            return Response({"error": "entity_key is required"}, status=status.HTTP_400_BAD_REQUEST)

        conflict_exists = KBEntity.objects.filter(entity_key=entity_key).exclude(id=entity.id).exists()
        if conflict_exists:
            return Response({"error": "entity_key already exists"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entity = replace_kb_entity(entity, payload)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(_serialize_entity(entity))

    def delete(self, request, entity_id, *args, **kwargs):
        denied = _staff_only(request)
        if denied is not None:
            return denied

        entity = get_object_or_404(KBEntity, id=entity_id)
        entity_key = entity.entity_key
        entity.delete()
        return Response({"deleted": True, "id": entity_id, "entity_key": entity_key})


class KBCandidateListView(APIView):
    def get(self, request, *args, **kwargs):
        denied = _auth_only(request)
        if denied is not None:
            return denied

        queryset = CandidateEntity.objects.all().select_related("approved_entity", "reviewed_by", "raw_upload").order_by("-id")
        upload_id = request.query_params.get("upload_id")
        status_value = (request.query_params.get("status") or "").strip().upper()
        if upload_id:
            queryset = queryset.filter(raw_upload_id=upload_id)
        if status_value:
            queryset = queryset.filter(status=status_value)

        if not request.user.is_staff:
            queryset = queryset.filter(raw_upload__uploaded_by=request.user)

        queryset = queryset[:200]
        return Response([_serialize_candidate(candidate, include_payload=False) for candidate in queryset])


class KBCandidateDetailView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def get(self, request, candidate_id, *args, **kwargs):
        denied = _auth_only(request)
        if denied is not None:
            return denied

        candidate = get_object_or_404(
            CandidateEntity.objects.select_related("approved_entity", "reviewed_by", "raw_upload"),
            id=candidate_id,
        )
        if not request.user.is_staff and candidate.raw_upload.uploaded_by_id != request.user.id:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response(_serialize_candidate(candidate))

    def patch(self, request, candidate_id, *args, **kwargs):
        denied = _staff_only(request)
        if denied is not None:
            return denied

        candidate = get_object_or_404(CandidateEntity, id=candidate_id)
        payload = request.data if isinstance(request.data, dict) else {}
        review_notes = payload.get("review_notes")

        try:
            if any(key in payload for key in ("entity_key", "canonical_key", "category", "source", "langs")):
                candidate = replace_candidate_entity(candidate, payload)
        except ValueError as exc:
            # 允许先保存草稿，不强制候选必须立刻满足术语入库条件
            if review_notes is not None:
                candidate.review_notes = str(review_notes or "")
                candidate.save(update_fields=["review_notes", "updated_at"])
            candidate = CandidateEntity.objects.select_related("approved_entity", "reviewed_by", "raw_upload").get(id=candidate.id)
            return Response(_serialize_candidate(candidate))

        if review_notes is not None:
            candidate.review_notes = str(review_notes or "")
            candidate.save(update_fields=["review_notes", "updated_at"])

        candidate = CandidateEntity.objects.select_related("approved_entity", "reviewed_by", "raw_upload").get(id=candidate.id)
        return Response(_serialize_candidate(candidate))


class KBCandidateApproveView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def post(self, request, candidate_id, *args, **kwargs):
        denied = _staff_only(request)
        if denied is not None:
            return denied

        candidate = get_object_or_404(CandidateEntity.objects.select_related("raw_upload"), id=candidate_id)
        if candidate.status == "APPROVED" and candidate.approved_entity_id:
            refreshed = CandidateEntity.objects.select_related("approved_entity", "reviewed_by", "raw_upload").get(id=candidate.id)
            return Response({"status": "already_approved", "candidate": _serialize_candidate(refreshed), "entity_id": refreshed.approved_entity_id})

        review_notes = (request.data.get("review_notes") or "").strip() if isinstance(request.data, dict) else ""
        try:
            candidate, entity, created = approve_candidate_entity(
                candidate,
                reviewed_by=request.user,
                review_notes=review_notes,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        candidate = CandidateEntity.objects.select_related("approved_entity", "reviewed_by", "raw_upload").get(id=candidate.id)
        return Response(
            {
                "status": "approved",
                "entity_created": created,
                "entity_id": entity.id,
                "candidate": _serialize_candidate(candidate),
            }
        )


class KBCandidateRejectView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def post(self, request, candidate_id, *args, **kwargs):
        denied = _staff_only(request)
        if denied is not None:
            return denied

        candidate = get_object_or_404(CandidateEntity.objects.select_related("raw_upload"), id=candidate_id)
        review_notes = (request.data.get("review_notes") or "").strip() if isinstance(request.data, dict) else ""
        candidate = reject_candidate_entity(candidate, reviewed_by=request.user, review_notes=review_notes)
        candidate = CandidateEntity.objects.select_related("approved_entity", "reviewed_by", "raw_upload").get(id=candidate.id)
        return Response({"status": "rejected", "candidate": _serialize_candidate(candidate)})


class KBDashboardRedirectView(TemplateView):
    template_name = "kb_dashboard_redirect.html"


class KBUserDashboardView(TemplateView):
    template_name = "kb_user_dashboard.html"


class KBManagementDashboardView(TemplateView):
    template_name = "kb_dashboard.html"


class KBUploadListView(APIView):
    def get(self, request, *args, **kwargs):
        denied = _auth_only(request)
        if denied is not None:
            return denied

        user = request.user
        try:
            raws = RawKBUpload.objects.all()
            if not user.is_staff:
                raws = raws.filter(uploaded_by=user)
            raws = raws.only("id", "status", "file_type", "uploaded_by", "created_at", "content").order_by("-id")[:100]
        except DatabaseError as exc:
            return Response(
                {
                    "error": "kb_uploads_query_failed",
                    "detail": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        data = []
        for raw in raws:
            data.append(
                {
                    "id": raw.id,
                    "status": raw.status,
                    "file_type": raw.file_type,
                    "uploaded_by": raw.uploaded_by.username if raw.uploaded_by else "",
                    "created_at": raw.created_at.isoformat() if raw.created_at else "",
                    "content_preview": _content_preview(raw.content),
                    "source_name": _upload_source_name(raw),
                    "can_process": bool(user.is_staff),
                }
            )
        return Response(data)


class KBSummaryView(APIView):
    def get(self, request, *args, **kwargs):
        denied = _auth_only(request)
        if denied is not None:
            return denied

        user = request.user
        if user.is_staff:
            uploads_qs = RawKBUpload.objects.all()
            candidates_qs = CandidateEntity.objects.all()
            entities_qs = KBEntity.objects.all()
        else:
            uploads_qs = RawKBUpload.objects.filter(uploaded_by=user)
            candidates_qs = CandidateEntity.objects.filter(raw_upload__uploaded_by=user)
            entities_qs = KBEntity.objects.filter(source__in=[
                _upload_source_name(raw) for raw in uploads_qs[:50]
            ])

        return Response({
            "upload_count": uploads_qs.count(),
            "candidate_count": candidates_qs.count(),
            "entity_count": entities_qs.count(),
        })


class KBUploadDetailView(APIView):
    def get(self, request, upload_id, *args, **kwargs):
        denied = _auth_only(request)
        if denied is not None:
            return denied

        raw = get_object_or_404(RawKBUpload, id=upload_id)
        user = request.user
        if not user.is_staff and raw.uploaded_by_id != user.id:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        return Response(_serialize_upload(raw, include_content=True))


class TranslateKBView(APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def post(self, request, entity_id, *args, **kwargs):
        denied = _staff_only(request)
        if denied is not None:
            return denied

        entity = get_object_or_404(KBEntity, id=entity_id)
        zh_block = entity.langs.get("zh", {})
        if not zh_block:
            return Response({"error": "no zh block"}, status=status.HTTP_400_BAD_REQUEST)

        target_langs = request.data.get("target_langs") or ["en", "ja", "fr", "de"]
        if isinstance(target_langs, str):
            target_langs = [lang.strip() for lang in target_langs.split(",") if lang.strip()]

        new_langs = translate_kb_entity(zh_block, target_langs=target_langs)
        entity, _ = upsert_kb_entity(
            {
                "entity_key": entity.entity_key,
                "canonical_key": entity.canonical_key,
                "category": entity.category,
                "source": entity.source,
                "langs": new_langs,
            }
        )

        return Response({"langs": entity.langs})


class BuildMultilangView(APIView):
    def post(self, request, *args, **kwargs):
        denied = _staff_only(request)
        if denied is not None:
            return denied

        result = build_multilang()
        return Response({"status": "done", **result})


class GenerateTrainingDataView(APIView):
    def post(self, request, *args, **kwargs):
        denied = _staff_only(request)
        if denied is not None:
            return denied

        try:
            stats = generate_training_data_main()
            return Response({"status": "done", "stats": stats})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TermCardsView(APIView):
    def get(self, request, entity_id: int, *args, **kwargs):
        denied = _auth_only(request)
        if denied is not None:
            return denied

        entity = get_object_or_404(KBEntity, id=entity_id)
        data = [
            {
                "lang": card.lang,
                "term": card.term,
                "type": card.type,
                "explain": card.explain_text,
            }
            for card in entity.term_cards.all().order_by("lang")
        ]
        return Response(data)
