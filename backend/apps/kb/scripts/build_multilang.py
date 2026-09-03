from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import faiss
import numpy as np
from django.db import DatabaseError

from backend.apps.kb.models import KBEntity
from backend.apps.kb.services import SUPPORTED_LANGS, TEXT_FIELDS, entity_to_export_record
from backend.core.embeddings.embedder import embed_texts

ROOT = Path(__file__).resolve().parents[4]
KB_DIR = ROOT / "backend" / "data" / "kb"

LANG_CODE_MAP = {
    "zh": "zho_Hans",
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "ja": "jpn_Jpan",
}

FIELD_LABELS = {
    "zh": {
        "definition": "定义",
        "symptoms": "症状",
        "diagnosis": "诊断",
        "treatment": "治疗",
        "notes": "说明",
    },
    "en": {
        "definition": "Definition",
        "symptoms": "Symptoms",
        "diagnosis": "Diagnosis",
        "treatment": "Treatment",
        "notes": "Notes",
    },
    "fr": {
        "definition": "Definition",
        "symptoms": "Symptoms",
        "diagnosis": "Diagnosis",
        "treatment": "Treatment",
        "notes": "Notes",
    },
    "de": {
        "definition": "Definition",
        "symptoms": "Symptoms",
        "diagnosis": "Diagnosis",
        "treatment": "Treatment",
        "notes": "Notes",
    },
    "ja": {
        "definition": "定義",
        "symptoms": "症状",
        "diagnosis": "診断",
        "treatment": "治療",
        "notes": "備考",
    },
}


def _norm(value: str) -> str:
    return (value or "").strip()


def _record_key(record: Dict[str, Any]) -> str:
    return (_norm(record.get("canonical_key")) or _norm(record.get("entity_id"))).lower()


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _dedupe_aliases(aliases: List[str], name: str = "") -> List[str]:
    out: List[str] = []
    seen = set()
    canonical = _norm(name)
    for alias in aliases or []:
        normalized = _norm(alias)
        if not normalized or normalized == canonical or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _merge_source_sections(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for item in (existing or []) + (incoming or []):
        source = _norm(item.get("source"))
        section_id = item.get("section_id")
        key = (source, section_id)
        if key in seen:
            continue
        seen.add(key)
        merged.append({"source": source, "section_id": section_id})
    return merged


def _merge_records(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = {
        "entity_id": _norm(incoming.get("entity_id")) or _norm(existing.get("entity_id")),
        "canonical_key": _norm(incoming.get("canonical_key")) or _norm(existing.get("canonical_key")),
        "category": _norm(incoming.get("category")) or _norm(existing.get("category")) or "unknown",
        "source": _norm(incoming.get("source")) or _norm(existing.get("source")) or "manual",
        "source_type": _norm(incoming.get("source_type")) or _norm(existing.get("source_type")) or "file",
        "source_sections": _merge_source_sections(
            existing.get("source_sections", []),
            incoming.get("source_sections", []),
        ),
        "lang_terms": {},
        "lang_texts": {},
    }

    all_langs = set((existing.get("lang_terms") or {}).keys()) | set((incoming.get("lang_terms") or {}).keys())
    for lang in all_langs:
        old_payload = (existing.get("lang_terms") or {}).get(lang, {}) or {}
        new_payload = (incoming.get("lang_terms") or {}).get(lang, {}) or {}
        name = _norm(new_payload.get("name")) or _norm(old_payload.get("name"))
        aliases = _dedupe_aliases(
            list(old_payload.get("aliases", []) or []) + list(new_payload.get("aliases", []) or []),
            name=name,
        )
        if name or aliases:
            merged["lang_terms"][lang] = {"name": name, "aliases": aliases}

    all_text_langs = set((existing.get("lang_texts") or {}).keys()) | set((incoming.get("lang_texts") or {}).keys())
    for lang in all_text_langs:
        old_bucket = (existing.get("lang_texts") or {}).get(lang, {}) or {}
        new_bucket = (incoming.get("lang_texts") or {}).get(lang, {}) or {}
        merged["lang_texts"][lang] = {
            field: _norm(new_bucket.get(field)) or _norm(old_bucket.get(field))
            for field in TEXT_FIELDS
        }

    return merged


def load_existing_entities(output_dir: Path) -> List[Dict[str, Any]]:
    data = _load_json(output_dir / "entities.json", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def build_term_index(entities: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    term_index = {lang: {} for lang in SUPPORTED_LANGS}
    for entity in entities:
        canonical_key = _norm(entity.get("canonical_key"))
        if not canonical_key:
            continue
        for lang, payload in (entity.get("lang_terms") or {}).items():
            if lang not in term_index or not isinstance(payload, dict):
                continue
            name = _norm(payload.get("name"))
            if name:
                term_index[lang][name] = canonical_key
            for alias in payload.get("aliases", []) or []:
                alias = _norm(alias)
                if alias:
                    term_index[lang][alias] = canonical_key
    return term_index


def build_full_text(lang: str, term: str, fields: Dict[str, str]) -> str:
    labels = FIELD_LABELS.get(lang, FIELD_LABELS["en"])
    lines = [term]
    for field in TEXT_FIELDS:
        value = _norm(fields.get(field))
        if value:
            lines.append(f"{labels[field]}: {value}")
    return "\n".join([line for line in lines if line]).strip()


def build_chunks(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for entity in entities:
        entity_id = _norm(entity.get("entity_id"))
        canonical_key = _norm(entity.get("canonical_key"))
        category = _norm(entity.get("category")) or "unknown"
        source = _norm(entity.get("source")) or "manual"
        source_type = _norm(entity.get("source_type")) or "file"

        for lang, term_payload in (entity.get("lang_terms") or {}).items():
            if lang not in SUPPORTED_LANGS:
                continue
            term = _norm(term_payload.get("name"))
            if not term:
                continue

            aliases = _dedupe_aliases(term_payload.get("aliases", []) or [], term)
            fields = (entity.get("lang_texts") or {}).get(lang, {}) or {}
            lang_code = LANG_CODE_MAP.get(lang, "")

            chunks.append(
                {
                    "chunk_id": f"{entity_id}_{lang}_term",
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "lang": lang,
                    "lang_code": lang_code,
                    "title": term,
                    "term": term,
                    "text_type": "term",
                    "text": f"Term: {term}\nCanonical: {canonical_key}\nCategory: {category}",
                    "aliases": aliases,
                    "category": category,
                    "source": source,
                    "source_type": source_type,
                }
            )

            for field in TEXT_FIELDS:
                value = _norm(fields.get(field))
                if not value:
                    continue
                chunks.append(
                    {
                        "chunk_id": f"{entity_id}_{lang}_{field}",
                        "entity_id": entity_id,
                        "canonical_key": canonical_key,
                        "lang": lang,
                        "lang_code": lang_code,
                        "title": term,
                        "term": term,
                        "text_type": field,
                        "text": f"{term}\n{field}: {value}",
                        "aliases": aliases,
                        "category": category,
                        "source": source,
                        "source_type": source_type,
                    }
                )

            full_text = build_full_text(lang, term, fields)
            if full_text:
                chunks.append(
                    {
                        "chunk_id": f"{entity_id}_{lang}_full",
                        "entity_id": entity_id,
                        "canonical_key": canonical_key,
                        "lang": lang,
                        "lang_code": lang_code,
                        "title": term,
                        "term": term,
                        "text_type": "full",
                        "text": full_text,
                        "aliases": aliases,
                        "category": category,
                        "source": source,
                        "source_type": source_type,
                    }
                )

    return chunks


def build_legacy_meta_from_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    meta: List[Dict[str, Any]] = []
    for chunk in chunks:
        meta.append(
            {
                "text": chunk.get("text", ""),
                "source_type": chunk.get("source_type", "file"),
                "source": chunk.get("source", "manual"),
                "title": chunk.get("title", ""),
                "term": chunk.get("term", ""),
                "lang": chunk.get("lang", ""),
                "lang_code": chunk.get("lang_code", ""),
                "category": chunk.get("category", ""),
                "entity_id": chunk.get("entity_id", ""),
                "text_type": chunk.get("text_type", ""),
                "chunk_id": chunk.get("chunk_id", ""),
                "canonical_key": chunk.get("canonical_key", ""),
                "aliases": chunk.get("aliases", []),
            }
        )
    return meta


def embed_chunks(chunks: List[Dict[str, Any]]) -> np.ndarray:
    embeddings = embed_texts([chunk["text"] for chunk in chunks])
    return np.asarray(embeddings, dtype=np.float32)


def save_outputs(
    output_dir: Path,
    entities: List[Dict[str, Any]],
    term_index: Dict[str, Dict[str, str]],
    chunks: List[Dict[str, Any]],
    legacy_meta: List[Dict[str, Any]],
    embeddings: np.ndarray,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    faiss.write_index(index, str(output_dir / "faiss.index"))
    (output_dir / "entities.json").write_text(json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "term_index.json").write_text(json.dumps(term_index, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "meta.json").write_text(json.dumps(legacy_meta, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_runtime_caches() -> None:
    try:
        from backend.apps.translation.term_matcher import _load_term_resources

        _load_term_resources.cache_clear()
    except Exception:
        pass

    try:
        from backend.core.rag import kb as kb_module

        kb_module._KB_CACHE = None
    except Exception:
        pass


def _is_valid_entity(record: Dict[str, Any]) -> bool:
    if not _record_key(record):
        return False
    lang_terms = record.get("lang_terms") or {}
    for payload in lang_terms.values():
        if _norm((payload or {}).get("name")):
            return True
    return False


def load_db_entities() -> tuple[List[Dict[str, Any]], str]:
    try:
        records = [entity_to_export_record(entity) for entity in KBEntity.objects.all().order_by("id")]
        return records, ""
    except DatabaseError as exc:
        return [], str(exc)


def build_multilang(kb_json_out: Path | None = None) -> Dict[str, Any]:
    output_dir = kb_json_out or KB_DIR
    existing_entities = load_existing_entities(output_dir)
    db_entities, db_error = load_db_entities()

    merged_by_key: Dict[str, Dict[str, Any]] = {}
    merged_entities: List[Dict[str, Any]] = []

    for record in existing_entities:
        key = _record_key(record)
        if not key:
            continue
        merged_by_key[key] = record
        merged_entities.append(record)

    for record in db_entities:
        key = _record_key(record)
        if not key:
            continue
        if key in merged_by_key:
            merged = _merge_records(merged_by_key[key], record)
            merged_by_key[key] = merged
            index = merged_entities.index(next(item for item in merged_entities if _record_key(item) == key))
            merged_entities[index] = merged
        else:
            merged_by_key[key] = record
            merged_entities.append(record)

    merged_entities = [record for record in merged_entities if _is_valid_entity(record)]
    if not merged_entities:
        raise RuntimeError("No valid KB entities available for export.")

    term_index = build_term_index(merged_entities)
    chunks = build_chunks(merged_entities)
    if not chunks:
        raise RuntimeError("No KB chunks generated from current entities.")

    legacy_meta = build_legacy_meta_from_chunks(chunks)
    embeddings = embed_chunks(chunks)
    if embeddings.ndim != 2 or embeddings.shape[0] != len(chunks):
        raise RuntimeError(f"Embedding shape mismatch: {embeddings.shape}, chunks={len(chunks)}")

    file_warning = ""
    active_output = True
    try:
        save_outputs(
            output_dir=output_dir,
            entities=merged_entities,
            term_index=term_index,
            chunks=chunks,
            legacy_meta=legacy_meta,
            embeddings=embeddings,
        )
    except PermissionError as exc:
        if output_dir != KB_DIR:
            raise
        file_warning = str(exc)
        output_dir = KB_DIR / "kb_app_generated"
        active_output = False
        save_outputs(
            output_dir=output_dir,
            entities=merged_entities,
            term_index=term_index,
            chunks=chunks,
            legacy_meta=legacy_meta,
            embeddings=embeddings,
        )

    if active_output:
        reset_runtime_caches()

    return {
        "output_dir": str(output_dir),
        "active_output": active_output,
        "entities_count": len(merged_entities),
        "db_entities_count": len(db_entities),
        "chunks_count": len(chunks),
        "db_warning": db_error,
        "file_warning": file_warning,
    }


if __name__ == "__main__":
    print(build_multilang())
