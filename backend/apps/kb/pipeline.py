from __future__ import annotations

from .models import CandidateEntity, KBEntity, RawKBUpload
from .scripts.build_multilang import build_multilang
from .services import extract_candidate_payloads, upsert_kb_entity
from .translator import translate_kb_entity


def build_candidates_from_raw(raw: RawKBUpload) -> list[CandidateEntity]:
    rows = extract_candidate_payloads(
        content=raw.content or "",
        source_name=(raw.file.name if raw.file else f"upload_{raw.id}"),
    )
    candidates: list[CandidateEntity] = []
    for row in rows:
        candidates.append(
            CandidateEntity.objects.create(
                raw_upload=raw,
                payload=row.get("payload") or {},
                extraction_method=row.get("extraction_method", ""),
                confidence=float(row.get("confidence") or 0.0),
                evidence_text=row.get("evidence_text", ""),
            )
        )
    return candidates


def run_kb_workflow_for_entity(entity_id: int) -> None:
    try:
        entity = KBEntity.objects.get(id=entity_id)
    except KBEntity.DoesNotExist:
        return

    zh_block = (entity.langs or {}).get("zh", {})
    if zh_block:
        translated = translate_kb_entity(zh_block, target_langs=["en", "ja", "fr", "de"])
        upsert_kb_entity(
            {
                "entity_key": entity.entity_key,
                "canonical_key": entity.canonical_key,
                "category": entity.category,
                "source": entity.source,
                "langs": translated,
            }
        )

    build_multilang()
