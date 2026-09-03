# backend/apps/translation/term_matcher.py
import json
import re
from pathlib import Path
from functools import lru_cache
from typing import List, Dict, Any, Tuple

from .manual_terms import MANUAL_ENTITIES

LANGS = {"zh", "en", "fr", "de", "ja"}


def _norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _norm_en(s: str) -> str:
    s = _norm_spaces(s).lower()
    s = s.strip(" .,:;()[]{}\"'“”‘’")
    return s


def _find_all_spans(text: str, keyword: str) -> List[Tuple[int, int]]:
    spans = []
    if not keyword:
        return spans
    start = 0
    while True:
        i = text.find(keyword, start)
        if i == -1:
            break
        spans.append((i, i + len(keyword)))
        start = i + len(keyword)
    return spans


def _is_cjk_lang(lang: str) -> bool:
    return lang in {"zh", "ja"}


def _concept_key_from_term(term: str) -> str:
    return _norm_en(term) or (term or "").strip()


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_db_entities() -> List[Dict[str, Any]]:
    try:
        from backend.apps.kb.models import KBEntity
        from backend.apps.kb.services import entity_to_export_record

        return [entity_to_export_record(entity) for entity in KBEntity.objects.all().order_by("id")]
    except Exception:
        return []


@lru_cache(maxsize=1)
def _load_term_resources():
    """
    加载：
    - term_index.json: {lang: {surface: canonical_key}}
    - entities.json:   [{canonical_key, category, lang_terms, ...}]
    """
    backend_dir = Path(__file__).resolve().parents[2]
    kb_dir = backend_dir / "data" / "kb"

    term_index_path = kb_dir / "term_index.json"
    entities_path = kb_dir / "entities.json"

    term_index = _load_json(term_index_path, {})
    entities = _load_json(entities_path, [])
    db_entities = _load_db_entities()

    entities_by_key = {}
    for e in entities:
        ck = (e.get("canonical_key") or "").strip()
        if ck:
            entities_by_key[ck] = e

    for e in db_entities:
        ck = (e.get("canonical_key") or "").strip()
        if ck:
            entities_by_key[ck] = e

        lang_terms = e.get("lang_terms") or {}
        for lang, payload in lang_terms.items():
            if lang not in LANGS or not isinstance(payload, dict):
                continue
            term_index.setdefault(lang, {})
            name = (payload.get("name") or "").strip()
            if name:
                term_index[lang][name] = ck
            for alias in payload.get("aliases") or []:
                alias = (alias or "").strip()
                if alias:
                    term_index[lang][alias] = ck

    for e in MANUAL_ENTITIES:
        ck = (e.get("canonical_key") or "").strip()
        if ck:
            entities_by_key[ck] = e
        lang_terms = e.get("lang_terms") or {}
        for lang, payload in lang_terms.items():
            if lang not in LANGS or not isinstance(payload, dict):
                continue
            term_index.setdefault(lang, {})
            name = (payload.get("name") or "").strip()
            if name:
                term_index[lang][name] = ck
            for alias in payload.get("aliases") or []:
                alias = (alias or "").strip()
                if alias:
                    term_index[lang][alias] = ck

    surfaces_by_lang = {}
    for lang in LANGS:
        mapping = term_index.get(lang, {}) or {}
        surfaces = list(mapping.keys())
        surfaces.sort(key=lambda x: len(x), reverse=True)
        surfaces_by_lang[lang] = surfaces

    return term_index, entities_by_key, surfaces_by_lang


def _get_entity_payload(canonical_key: str) -> Dict[str, Any]:
    _, entities_by_key, _ = _load_term_resources()
    return entities_by_key.get(canonical_key) or {}


def get_entity_payload(canonical_key: str) -> Dict[str, Any]:
    return _get_entity_payload(canonical_key)


def _entity_lang_name(entity: Dict[str, Any], lang: str) -> str:
    lang_terms = entity.get("lang_terms") or {}
    payload = lang_terms.get(lang) or {}
    return (payload.get("name") or "").strip()


def _entity_aliases(entity: Dict[str, Any], lang: str) -> List[str]:
    lang_terms = entity.get("lang_terms") or {}
    payload = lang_terms.get(lang) or {}
    aliases = payload.get("aliases") or []
    return [x.strip() for x in aliases if (x or "").strip()]


def _dedupe_overlaps(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not hits:
        return []

    hits_sorted = sorted(
        hits,
        key=lambda x: (x["span"][0], -(x["span"][1] - x["span"][0]))
    )

    kept = []
    occupied = []

    def overlap(a, b):
        return not (a[1] <= b[0] or b[1] <= a[0])

    for h in hits_sorted:
        s, e = h["span"]
        cur = (s, e)
        if any(overlap(cur, occ) for occ in occupied):
            continue
        kept.append(h)
        occupied.append(cur)

    kept.sort(key=lambda x: (x["span"][0], -(x["span"][1] - x["span"][0])))
    return kept


def _dedupe_by_concept(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best = {}
    for h in hits:
        ck = h.get("concept_key") or ""
        cur = best.get(ck)
        if cur is None:
            best[ck] = h
            continue

        s, e = h["span"]
        s2, e2 = cur["span"]

        if (e - s) > (e2 - s2) or ((e - s) == (e2 - s2) and s < s2):
            best[ck] = h

    out = list(best.values())
    out.sort(key=lambda x: (x["span"][0], -(x["span"][1] - x["span"][0])))
    return out


def _build_hit(
    text: str,
    s: int,
    e: int,
    matched_surface: str,
    canonical_key: str,
    lang: str,
) -> Dict[str, Any]:
    entity = _get_entity_payload(canonical_key)
    category = (entity.get("category") or "").strip() or "term"

    return {
        "term": matched_surface,
        "span": [s, e],
        "lang": lang,
        "type": category,
        "concept_key": canonical_key,
        "canonical_key": canonical_key,
        "entity_id": entity.get("entity_id", ""),

        # 兼容旧前端
        "zh": _entity_lang_name(entity, "zh"),
        "term_en": _entity_lang_name(entity, "en"),

        # 新增多语言字段
        "term_zh": _entity_lang_name(entity, "zh"),
        "term_en_full": _entity_lang_name(entity, "en"),
        "term_fr": _entity_lang_name(entity, "fr"),
        "term_de": _entity_lang_name(entity, "de"),
        "term_ja": _entity_lang_name(entity, "ja"),

        "aliases": _entity_aliases(entity, lang),
        "matched_text": text[s:e],
    }


def _match_cjk_terms(text: str, lang: str, limit: int) -> List[Dict[str, Any]]:
    term_index, _, surfaces_by_lang = _load_term_resources()
    mapping = term_index.get(lang, {}) or {}
    surfaces = surfaces_by_lang.get(lang, []) or []

    hits = []
    used = set()

    for surface in surfaces:
        if not surface:
            continue
        for s, e in _find_all_spans(text, surface):
            if (s, e) in used:
                continue
            used.add((s, e))
            ck = mapping.get(surface) or _concept_key_from_term(surface)
            hits.append(_build_hit(text, s, e, surface, ck, lang))
            if len(hits) >= limit:
                return hits
    return hits


def _match_latin_terms(text: str, lang: str, limit: int) -> List[Dict[str, Any]]:
    term_index, _, surfaces_by_lang = _load_term_resources()
    mapping = term_index.get(lang, {}) or {}
    surfaces = surfaces_by_lang.get(lang, []) or []

    hits = []
    used = set()

    for surface in surfaces:
        surface = (surface or "").strip()
        if not surface:
            continue

        # 单词边界更安全，适合 en/fr/de
        pattern = re.compile(rf"(?<!\w){re.escape(surface)}(?!\w)", re.IGNORECASE)
        for m in pattern.finditer(text):
            s, e = m.start(), m.end()
            if (s, e) in used:
                continue
            used.add((s, e))
            ck = mapping.get(surface) or _concept_key_from_term(surface)
            hits.append(_build_hit(text, s, e, m.group(0), ck, lang))
            if len(hits) >= limit:
                return hits
    return hits


def extract_terms_for_text(
    text: str,
    lang: str = "zh",
    limit: int = 80,
    min_len_zh: int = 2,
) -> List[Dict[str, Any]]:
    """
    基于 term_index.json + entities.json 做多语言术语抽取/高亮。

    支持:
    - zh
    - en
    - fr
    - de
    - ja
    """
    text = text or ""
    lang = (lang or "zh").strip().lower()

    if not text.strip():
        return []

    if lang not in LANGS:
        lang = "zh"

    hits: List[Dict[str, Any]] = []

    if _is_cjk_lang(lang):
        hits = _match_cjk_terms(text, lang, limit=limit)
        if lang == "zh":
            hits = [h for h in hits if len(h.get("term", "")) >= min_len_zh]
    else:
        hits = _match_latin_terms(text, lang, limit=limit)

    hits = _dedupe_overlaps(hits)
    hits = _dedupe_by_concept(hits)

    return hits[:limit]
