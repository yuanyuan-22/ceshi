from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from django.db import DatabaseError, transaction
from django.utils import timezone

from .models import CandidateEntity, KBEntity, RawKBUpload, TermCard

SUPPORTED_LANGS = ("zh", "en", "ja", "fr", "de")
TEXT_FIELDS = ("definition", "symptoms", "diagnosis", "treatment", "notes")
MAX_CANDIDATES_PER_UPLOAD = 24

CATEGORY_KEYWORDS = {
    "disease": (
        "病", "炎", "症", "癌", "综合征", "感染", "瘤", "disease", "syndrome",
        "infection", "cancer", "itis", "tumor", "tumour",
    ),
    "symptom": (
        "痛", "热", "咳", "喘", "头晕", "恶心", "呕吐", "symptom", "pain",
        "fever", "cough", "nausea", "vomiting",
    ),
    "drug": (
        "片", "胶囊", "注射液", "药", "剂", "tablet", "capsule", "injection",
        "drug", "medicine",
    ),
    "examination": (
        "检查", "检验", "筛查", "测定", "test", "exam", "examination",
        "screening", "assay",
    ),
    "treatment": (
        "治疗", "手术", "疗法", "康复", "treatment", "therapy", "surgery",
        "rehabilitation",
    ),
}

FIELD_HINTS = {
    "zh": {
        "definition": ("定义", "是指", "是一种", "属于", "是由"),
        "symptoms": ("症状", "表现", "可出现", "常见表现", "临床表现"),
        "diagnosis": ("诊断", "检查", "检验", "筛查", "确诊"),
        "treatment": ("治疗", "处理", "用药", "干预", "缓解"),
        "notes": ("注意", "提示", "说明", "预后", "鉴别"),
    },
    "en": {
        "definition": ("definition", "is a", "is an", "refers to", "defined as"),
        "symptoms": ("symptom", "symptoms", "presents with", "manifestation"),
        "diagnosis": ("diagnosis", "diagnosed", "exam", "test", "screening"),
        "treatment": ("treatment", "therapy", "managed with", "medication"),
        "notes": ("note", "notes", "warning", "prognosis", "distinguish"),
    },
}

ZH_TERM_STOPWORDS = {
    "主要", "常见", "患者", "疾病", "症状", "治疗", "诊断", "定义", "说明",
    "感染", "表现", "情况",
}

EN_TERM_STOPWORDS = {
    "patient", "patients", "disease", "symptoms", "treatment", "diagnosis",
    "definition", "note", "notes", "common",
}

MANUAL_REVIEW_PLACEHOLDERS = {
    "待人工整理",
    "manual_review_required",
    "manual review",
}


def _norm_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _norm_key(value: str) -> str:
    return _norm_spaces(value).lower()


def slugify_key(value: str) -> str:
    value = _norm_key(value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", value)
    value = value.strip("_")
    return value or "kb_entity"


def parse_aliases(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[;,，；、/]+", str(value or ""))

    items: List[str] = []
    seen = set()
    for item in raw_items:
        normalized = _norm_spaces(str(item))
        if normalized and normalized not in seen:
            seen.add(normalized)
            items.append(normalized)
    return items


def dedupe_values(values: Iterable[str], skip_value: str = "") -> List[str]:
    out: List[str] = []
    seen = set()
    skip_key = _norm_key(skip_value)
    for value in values or []:
        normalized = _norm_spaces(str(value))
        key = _norm_key(normalized)
        if not normalized or key == skip_key or key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def parse_key_value_lines(block_text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for raw_line in (block_text or "").splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "aliases":
            result[key] = parse_aliases(value)
        else:
            result[key] = value
    return result


def split_entity_blocks(raw_text: str) -> List[str]:
    parts = re.split(r"(?m)^\[ENTITY\]\s*$", raw_text or "")
    return [part.strip() for part in parts if part.strip()]


def split_lang_blocks(entity_block: str) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    lang_parts = re.split(r"(?m)^\[LANG:([a-z]{2})\]\s*$", entity_block or "")
    head_text = lang_parts[0].strip() if lang_parts else ""
    entity_meta = parse_key_value_lines(head_text)
    lang_payloads: Dict[str, Dict[str, Any]] = {}

    index = 1
    while index + 1 < len(lang_parts):
        lang = (lang_parts[index] or "").strip().lower()
        payload_text = lang_parts[index + 1] or ""
        index += 2
        if lang not in SUPPORTED_LANGS:
            continue
        payload = parse_key_value_lines(payload_text)
        if payload:
            lang_payloads[lang] = payload

    return entity_meta, lang_payloads


def _build_lang_block(payload: Dict[str, Any], fallback_term: str = "") -> Dict[str, Any]:
    aliases = parse_aliases(payload.get("aliases", []))
    term = _norm_spaces(payload.get("term") or payload.get("name") or fallback_term)
    block: Dict[str, Any] = {
        "term": term,
        "aliases": aliases,
    }
    for field in TEXT_FIELDS:
        block[field] = _norm_spaces(payload.get(field, ""))
    return block


def _build_fallback_payload(
    content: str,
    source_name: str,
    default_term: str,
    default_category: str,
    default_canonical_key: str,
) -> List[Dict[str, Any]]:
    key_values = parse_key_value_lines(content)
    term = _norm_spaces(key_values.get("term") or default_term)
    canonical_key = _norm_spaces(key_values.get("canonical_key") or default_canonical_key or term)
    category = _norm_spaces(key_values.get("category") or default_category or "unknown")
    source = _norm_spaces(key_values.get("source") or source_name or "manual")

    if any(field in key_values for field in ("term", *TEXT_FIELDS)):
        zh_block = _build_lang_block(key_values, fallback_term=term)
    else:
        zh_block = {
            "term": term,
            "aliases": [],
            "definition": _norm_spaces(content),
            "symptoms": "",
            "diagnosis": "",
            "treatment": "",
            "notes": "",
        }

    entity_key_seed = canonical_key or term or "upload"
    return [{
        "entity_key": key_values.get("id") or f"kb_{slugify_key(entity_key_seed)}",
        "canonical_key": canonical_key or entity_key_seed,
        "category": category,
        "source": source,
        "langs": {"zh": zh_block},
    }]


def parse_kb_payloads(
    content: str,
    source_name: str = "manual",
    default_term: str = "",
    default_category: str = "unknown",
    default_canonical_key: str = "",
) -> List[Dict[str, Any]]:
    raw_text = (content or "").strip()
    if not raw_text:
        return []

    has_structured_blocks = "[LANG:" in raw_text or "[ENTITY]" in raw_text
    if not has_structured_blocks:
        return _build_fallback_payload(
            content=raw_text,
            source_name=source_name,
            default_term=default_term,
            default_category=default_category,
            default_canonical_key=default_canonical_key,
        )

    payloads: List[Dict[str, Any]] = []
    blocks = split_entity_blocks(raw_text)
    if not blocks:
        blocks = [raw_text]

    seen_keys: Dict[str, int] = {}

    for ordinal, block in enumerate(blocks, start=1):
        entity_meta, lang_payloads = split_lang_blocks(block)
        if not lang_payloads:
            continue

        canonical_key = _norm_spaces(
            entity_meta.get("canonical_key")
            or default_canonical_key
            or (lang_payloads.get("en") or {}).get("term")
            or (lang_payloads.get("zh") or {}).get("term")
        )
        category = _norm_spaces(entity_meta.get("category") or default_category or "unknown")
        source = _norm_spaces(entity_meta.get("source") or source_name or "manual")
        entity_key = _norm_spaces(entity_meta.get("id") or f"kb_{slugify_key(canonical_key or f'upload_{ordinal}')}")

        if entity_key in seen_keys:
            seen_keys[entity_key] += 1
            entity_key = f"{entity_key}_{seen_keys[entity_key]}"
        else:
            seen_keys[entity_key] = 1

        langs: Dict[str, Dict[str, Any]] = {}
        for lang, lang_payload in lang_payloads.items():
            langs[lang] = _build_lang_block(lang_payload)

        if not any((block.get("term") or "") for block in langs.values()):
            continue

        payloads.append({
            "entity_key": entity_key,
            "canonical_key": canonical_key or entity_key,
            "category": category,
            "source": source,
            "langs": langs,
        })

    return payloads


def _split_sentences(text: str, lang: str) -> List[str]:
    raw = _norm_spaces(text)
    if not raw:
        return []

    if lang == "zh":
        parts = re.split(r"[。！？；;]\s*", raw)
    else:
        parts = re.split(r"(?<=[\.\!\?;])\s+", raw)
    return [_norm_spaces(part) for part in parts if _norm_spaces(part)]


def _split_free_text_blocks(content: str) -> List[str]:
    raw = str(content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return []

    paragraph_blocks = [_norm_spaces(block) for block in re.split(r"\n\s*\n+", raw) if _norm_spaces(block)]
    if len(paragraph_blocks) > 1:
        return paragraph_blocks

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) <= 1:
        return [raw]

    blocks: List[str] = []
    current: List[str] = []
    for line in lines:
        is_heading = len(line) <= 32 and not re.search(r"[。！？;；:：]", line)
        if is_heading and current:
            blocks.append(_norm_spaces(" ".join(current)))
            current = [line]
            continue
        current.append(line)

    if current:
        blocks.append(_norm_spaces(" ".join(current)))
    return blocks or [raw]


def _detect_content_lang(text: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", str(text or "")) else "en"


def _clean_term_candidate(value: str) -> str:
    term = _norm_spaces(value)
    term = re.sub(r"^[\-\*\d\.\)\(、\s]+", "", term)
    term = term.strip("“”\"'`[]【】<>《》()（）,.;:：，。； ")
    term = re.sub(r"^(患者|考虑|诊断为|疑似|关于|有关)", "", term)
    return _norm_spaces(term)


def _split_alias_blob(value: str) -> List[str]:
    return parse_aliases(re.split(r"[、,，;/；]|(?:\band\b)|(?:\bor\b)", str(value or ""), flags=re.IGNORECASE))


def _lang_has_term(text: str, term: str, lang: str) -> bool:
    text_norm = _norm_key(text)
    term_norm = _norm_key(term)
    if not text_norm or not term_norm:
        return False
    if lang == "zh":
        return term_norm in text_norm
    return bool(re.search(rf"\b{re.escape(term_norm)}\b", text_norm))


def _guess_category(*values: str) -> str:
    combined = _norm_key(" ".join([value for value in values if value]))
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if _norm_key(keyword) in combined:
                return category
    return "unknown"


def _extract_aliases_from_text(text: str, lang: str, term: str = "") -> List[str]:
    patterns = [
        r"(?:别名|又称|俗称|也称)[:：]?\s*([^\n。；;]{1,80})",
        r"(?:also called|also known as|aliases?)[:\s]+([^\n\.]{1,120})",
    ]
    aliases: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, str(text or ""), flags=re.IGNORECASE):
            aliases.extend(_split_alias_blob(match.group(1)))
    return dedupe_values(aliases, term)


def _is_plausible_candidate_term(term: str, lang: str) -> bool:
    term = _clean_term_candidate(term)
    if not term:
        return False
    if lang == "zh":
        if len(term) < 2 or len(term) > 40:
            return False
        return term not in ZH_TERM_STOPWORDS
    term_key = _norm_key(term)
    if len(term_key) < 3 or len(term_key) > 60:
        return False
    return term_key not in EN_TERM_STOPWORDS


def _extract_text_fields_from_block(block_text: str, term: str, lang: str) -> Dict[str, str]:
    sentences = _split_sentences(block_text, lang)
    buckets: Dict[str, List[str]] = {field: [] for field in TEXT_FIELDS}
    leftovers: List[str] = []
    hints = FIELD_HINTS.get(lang, FIELD_HINTS["en"])

    for sentence in sentences:
        sentence_norm = _norm_key(sentence)
        matched_field = ""
        for field in TEXT_FIELDS:
            keywords = hints.get(field, ())
            if any(_norm_key(keyword) in sentence_norm for keyword in keywords):
                matched_field = field
                break

        if not matched_field and term and _lang_has_term(sentence, term, lang):
            if re.search(r"(是一种|是指|属于|是由| is a | is an | refers to | defined as )", sentence_norm):
                matched_field = "definition"

        if matched_field:
            if sentence not in buckets[matched_field]:
                buckets[matched_field].append(sentence)
        else:
            leftovers.append(sentence)

    if not buckets["definition"] and sentences:
        first_sentence = sentences[0]
        if term and (_lang_has_term(first_sentence, term, lang) or len(sentences) == 1):
            buckets["definition"].append(first_sentence)

    if not buckets["notes"] and leftovers:
        buckets["notes"] = leftovers[:2]

    return {
        field: _norm_spaces(" ".join(buckets[field][:2]))
        for field in TEXT_FIELDS
    }


def _find_existing_entity_match(term: str, lang: str) -> KBEntity | None:
    needle = _norm_key(term)
    if not needle:
        return None

    try:
        queryset = KBEntity.objects.all().only("id", "entity_key", "canonical_key", "langs")
        for entity in queryset:
            payload = (entity.langs or {}).get(lang) or {}
            names = [payload.get("term")] + list(payload.get("aliases", []) or [])
            for name in names:
                if _norm_key(name) == needle:
                    return entity
    except DatabaseError:
        return None
    return None


def _first_term_from_langs(langs_payload: Dict[str, Dict[str, Any]]) -> str:
    for lang in ("zh", "en", "ja", "fr", "de"):
        payload = (langs_payload or {}).get(lang) or {}
        term = _norm_spaces(payload.get("term") or "")
        if term:
            return term
    return ""


def _primary_lang_from_payload(langs_payload: Dict[str, Dict[str, Any]]) -> str:
    for lang in ("zh", "en", "ja", "fr", "de"):
        if isinstance((langs_payload or {}).get(lang), dict):
            return lang
    return next(iter(langs_payload or {}), "zh")


def _hydrate_missing_candidate_term(payload: Dict[str, Any]) -> Dict[str, Any]:
    hydrated = dict(payload or {})
    langs = dict(hydrated.get("langs") or {})
    if not langs:
        hydrated["langs"] = langs
        return hydrated

    canonical_key = _norm_spaces(hydrated.get("canonical_key") or "")
    primary_lang = _primary_lang_from_payload(langs)
    block = dict(langs.get(primary_lang) or {})
    term = _norm_spaces(block.get("term") or "")

    if not term and canonical_key and canonical_key.lower() not in {item.lower() for item in MANUAL_REVIEW_PLACEHOLDERS}:
        block["term"] = canonical_key
        langs[primary_lang] = block

    hydrated["langs"] = langs
    return hydrated


def sanitize_candidate_payload(payload: Dict[str, Any], fallback_source: str = "manual") -> Dict[str, Any]:
    sanitized = _hydrate_missing_candidate_term(payload or {})
    langs = sanitize_langs_payload(sanitized.get("langs") or {})
    if not langs:
        raise ValueError("at least one language block is required")
    term_seed = _first_term_from_langs(langs)
    canonical_key = _norm_spaces(sanitized.get("canonical_key") or term_seed)
    entity_key = _norm_spaces(sanitized.get("entity_key") or "")
    if not entity_key:
        entity_key = f"kb_{slugify_key(canonical_key or term_seed or 'candidate')}"
    if not canonical_key:
        canonical_key = entity_key

    return {
        "entity_key": entity_key,
        "canonical_key": canonical_key,
        "category": _norm_spaces(sanitized.get("category") or "unknown"),
        "source": _norm_spaces(sanitized.get("source") or fallback_source or "manual"),
        "langs": langs,
    }


def _candidate_record(
    payload: Dict[str, Any],
    *,
    confidence: float,
    extraction_method: str,
    evidence_text: str,
    fallback_source: str,
) -> Dict[str, Any]:
    return {
        "payload": sanitize_candidate_payload(payload, fallback_source=fallback_source),
        "confidence": max(0.0, min(float(confidence), 0.99)),
        "extraction_method": extraction_method,
        "evidence_text": str(evidence_text or "").strip(),
    }


def _build_manual_review_candidate(raw_text: str, source_name: str) -> Dict[str, Any]:
    lang = _detect_content_lang(raw_text)
    notes = _norm_spaces(raw_text)
    truncated_notes = notes[:1200]
    payload = {
        "entity_key": f"kb_manual_review_{slugify_key(source_name or 'upload')}",
        "canonical_key": "待人工整理",
        "category": "unknown",
        "source": source_name,
        "langs": {
            lang: {
                "term": "",
                "aliases": [],
                "definition": "",
                "symptoms": "",
                "diagnosis": "",
                "treatment": "",
                "notes": truncated_notes,
            }
        },
    }
    return _candidate_record(
        payload,
        confidence=0.2,
        extraction_method="manual_review_required",
        evidence_text=raw_text,
        fallback_source=source_name,
    )


def _find_term_candidates(block_text: str, lang: str) -> List[str]:
    patterns = []
    if lang == "zh":
        patterns = [
            r"([\u4e00-\u9fffA-Za-z0-9\-·()（）]{2,40}?)(?:又称|俗称|别名|是一种|是指|属于|表现为)",
            r"([\u4e00-\u9fffA-Za-z0-9\-·()（）]{2,40}?)(?:症状|诊断|治疗|定义)[:：]",
        ]
    else:
        patterns = [
            r"([A-Z][A-Za-z0-9\-\s]{2,60}?)(?: is | refers to |, also called |, also known as )",
            r"([A-Z][A-Za-z0-9\-\s]{2,60}?)(?: symptoms| diagnosis| treatment| definition)[:]",
        ]

    terms: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, block_text, flags=re.IGNORECASE):
            term = _clean_term_candidate(match.group(1))
            if term:
                terms.append(term)

    if not terms:
        first_sentence = _split_sentences(block_text, lang)
        if first_sentence:
            sentence = first_sentence[0]
            if lang == "zh":
                m = re.match(r"^([\u4e00-\u9fffA-Za-z0-9\-·()（）]{2,40}?)(?:是|属于|又称|俗称)", sentence)
            else:
                m = re.match(r"^([A-Z][A-Za-z0-9\-\s]{2,60}?)(?: is | refers to )", sentence, flags=re.IGNORECASE)
            if m:
                term = _clean_term_candidate(m.group(1))
                if term:
                    terms.append(term)

    if not terms:
        lines = [line.strip() for line in str(block_text or "").splitlines() if line.strip()]
        if lines:
            first_line = _clean_term_candidate(lines[0])
            if first_line and len(first_line) <= 40 and not re.search(r"[。！？;；]", first_line):
                terms.append(first_line)

    deduped: List[str] = []
    seen = set()
    for term in terms:
        key = _norm_key(term)
        if not key or key in seen or not _is_plausible_candidate_term(term, lang):
            continue
        seen.add(key)
        deduped.append(term)
    return deduped[:3]


def _build_heuristic_candidate(
    block_text: str,
    term: str,
    *,
    source_name: str,
) -> Dict[str, Any] | None:
    lang = _detect_content_lang(block_text)
    clean_term = _clean_term_candidate(term)
    if not clean_term:
        return None

    aliases = _extract_aliases_from_text(block_text, lang, clean_term)
    fields = _extract_text_fields_from_block(block_text, clean_term, lang)
    category = _guess_category(clean_term, block_text)
    existing_entity = _find_existing_entity_match(clean_term, lang)
    canonical_key = existing_entity.canonical_key if existing_entity else (clean_term.lower() if lang == "en" else clean_term)
    entity_key = existing_entity.entity_key if existing_entity else f"kb_{slugify_key(canonical_key or clean_term)}"
    confidence = 0.66
    if fields.get("definition"):
        confidence += 0.1
    if aliases:
        confidence += 0.05
    if category != "unknown":
        confidence += 0.04

    return _candidate_record(
        {
            "entity_key": entity_key,
            "canonical_key": canonical_key,
            "category": category,
            "source": source_name,
            "langs": {
                lang: {
                    "term": clean_term,
                    "aliases": aliases,
                    **fields,
                }
            },
        },
        confidence=confidence,
        extraction_method="heuristic_free_text",
        evidence_text=block_text,
        fallback_source=source_name,
    )


def extract_candidate_payloads(
    content: str,
    source_name: str = "manual",
    default_term: str = "",
    default_category: str = "unknown",
    default_canonical_key: str = "",
) -> List[Dict[str, Any]]:
    raw_text = (content or "").strip()
    if not raw_text:
        return []

    if "[LANG:" in raw_text or "[ENTITY]" in raw_text:
        payloads = parse_kb_payloads(
            content=raw_text,
            source_name=source_name,
            default_term=default_term,
            default_category=default_category,
            default_canonical_key=default_canonical_key,
        )
        return [
            _candidate_record(
                payload,
                confidence=0.98,
                extraction_method="structured_block",
                evidence_text=raw_text,
                fallback_source=source_name,
            )
            for payload in payloads
        ]

    key_values = parse_key_value_lines(raw_text)
    if any(field in key_values for field in ("term", "aliases", *TEXT_FIELDS)):
        payload = _build_fallback_payload(
            content=raw_text,
            source_name=source_name,
            default_term=default_term,
            default_category=default_category,
            default_canonical_key=default_canonical_key,
        )[0]
        return [
            _candidate_record(
                payload,
                confidence=0.92 if key_values.get("term") else 0.84,
                extraction_method="key_value_block",
                evidence_text=raw_text,
                fallback_source=source_name,
            )
        ]

    candidates: List[Dict[str, Any]] = []
    seen = set()
    for block in _split_free_text_blocks(raw_text):
        lang = _detect_content_lang(block)
        for term in _find_term_candidates(block, lang):
            candidate = _build_heuristic_candidate(block, term, source_name=source_name)
            if not candidate:
                continue
            entity_key = _norm_key((candidate.get("payload") or {}).get("entity_key"))
            if entity_key in seen:
                continue
            seen.add(entity_key)
            candidates.append(candidate)
            if len(candidates) >= MAX_CANDIDATES_PER_UPLOAD:
                return candidates

    if candidates:
        return candidates

    return [_build_manual_review_candidate(raw_text, source_name)]


def _merge_lang_block(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing or {})
    incoming_aliases = parse_aliases(incoming.get("aliases", []))
    existing_aliases = parse_aliases(merged.get("aliases", []))
    merged_aliases = list(existing_aliases)
    seen = set(existing_aliases)
    for alias in incoming_aliases:
        if alias not in seen and alias != _norm_spaces(incoming.get("term", "")):
            seen.add(alias)
            merged_aliases.append(alias)

    term = _norm_spaces(incoming.get("term") or merged.get("term") or "")
    merged["term"] = term
    merged["aliases"] = merged_aliases

    for field in TEXT_FIELDS:
        value = _norm_spaces(incoming.get(field) or "")
        if value:
            merged[field] = value
        else:
            merged.setdefault(field, _norm_spaces(merged.get(field) or ""))

    return merged


def build_term_card_payloads(entity: KBEntity) -> List[Dict[str, str]]:
    cards: List[Dict[str, str]] = []
    langs = entity.langs or {}
    for lang in SUPPORTED_LANGS:
        payload = langs.get(lang)
        if not isinstance(payload, dict):
            continue

        term = _norm_spaces(payload.get("term") or "")
        explain = ""
        for field in ("definition", "notes", "symptoms", "diagnosis", "treatment"):
            value = _norm_spaces(payload.get(field) or "")
            if value:
                explain = value
                break

        if not term and not explain:
            continue

        cards.append({
            "lang": lang,
            "term": term,
            "type": entity.category or "term",
            "explain_text": explain,
        })
    return cards


def sync_term_cards(entity: KBEntity) -> None:
    TermCard.objects.filter(entity=entity).delete()
    cards = build_term_card_payloads(entity)
    if cards:
        TermCard.objects.bulk_create(
            [
                TermCard(
                    entity=entity,
                    lang=card["lang"],
                    term=card["term"],
                    type=card["type"],
                    explain_text=card["explain_text"],
                )
                for card in cards
            ]
        )


def sanitize_langs_payload(langs_payload: Any) -> Dict[str, Dict[str, Any]]:
    sanitized: Dict[str, Dict[str, Any]] = {}
    if not isinstance(langs_payload, dict):
        return sanitized

    for lang, payload in langs_payload.items():
        if lang not in SUPPORTED_LANGS or not isinstance(payload, dict):
            continue

        block = _build_lang_block(payload)
        has_content = bool(
            block.get("term")
            or block.get("aliases")
            or any(block.get(field) for field in TEXT_FIELDS)
        )
        if has_content:
            sanitized[lang] = block

    return sanitized


@transaction.atomic
def upsert_kb_entity(payload: Dict[str, Any]) -> Tuple[KBEntity, bool]:
    entity_key = _norm_spaces(payload.get("entity_key") or "")
    if not entity_key:
        raise ValueError("entity_key is required")

    entity, created = KBEntity.objects.get_or_create(
        entity_key=entity_key,
        defaults={
            "canonical_key": _norm_spaces(payload.get("canonical_key") or ""),
            "category": _norm_spaces(payload.get("category") or "unknown"),
            "source": _norm_spaces(payload.get("source") or "manual"),
            "langs": {},
        },
    )

    if not created:
        if payload.get("canonical_key"):
            entity.canonical_key = _norm_spaces(payload.get("canonical_key") or entity.canonical_key)
        if payload.get("category"):
            entity.category = _norm_spaces(payload.get("category") or entity.category)
        if payload.get("source"):
            entity.source = _norm_spaces(payload.get("source") or entity.source)

    merged_langs = dict(entity.langs or {})
    for lang, lang_payload in (payload.get("langs") or {}).items():
        if lang not in SUPPORTED_LANGS or not isinstance(lang_payload, dict):
            continue
        merged_langs[lang] = _merge_lang_block(merged_langs.get(lang, {}), lang_payload)

    entity.langs = merged_langs
    entity.save()
    sync_term_cards(entity)
    clear_translation_term_cache()
    return entity, created


@transaction.atomic
def replace_kb_entity(entity: KBEntity, payload: Dict[str, Any]) -> KBEntity:
    entity_key = _norm_spaces(payload.get("entity_key") or entity.entity_key)
    if not entity_key:
        raise ValueError("entity_key is required")

    entity.entity_key = entity_key
    entity.canonical_key = _norm_spaces(payload.get("canonical_key") or entity.canonical_key or entity_key)
    entity.category = _norm_spaces(payload.get("category") or entity.category or "unknown")
    entity.source = _norm_spaces(payload.get("source") or entity.source or "manual")

    if "langs" in payload:
        langs = sanitize_langs_payload(payload.get("langs") or {})
        if not langs:
            raise ValueError("at least one language block is required")
        entity.langs = langs

    entity.save()
    sync_term_cards(entity)
    clear_translation_term_cache()
    return entity


def entity_to_export_record(entity: KBEntity) -> Dict[str, Any]:
    langs = entity.langs or {}
    lang_terms: Dict[str, Dict[str, Any]] = {}
    lang_texts: Dict[str, Dict[str, str]] = {}

    for lang, payload in langs.items():
        if lang not in SUPPORTED_LANGS or not isinstance(payload, dict):
            continue

        term = _norm_spaces(payload.get("term") or payload.get("name") or "")
        aliases = parse_aliases(payload.get("aliases", []))
        if term or aliases:
            lang_terms[lang] = {
                "name": term,
                "aliases": [alias for alias in aliases if alias and alias != term],
            }

        lang_texts[lang] = {
            field: _norm_spaces(payload.get(field) or "")
            for field in TEXT_FIELDS
        }

    return {
        "entity_id": entity.entity_key,
        "canonical_key": entity.canonical_key or entity.entity_key,
        "category": entity.category or "unknown",
        "source": entity.source or "manual",
        "source_type": "db",
        "source_sections": [],
        "lang_terms": lang_terms,
        "lang_texts": lang_texts,
    }


def refresh_term_cards_for_entities(entities: Iterable[KBEntity]) -> None:
    for entity in entities:
        sync_term_cards(entity)


def clear_translation_term_cache() -> None:
    try:
        from backend.apps.translation.term_matcher import _load_term_resources

        _load_term_resources.cache_clear()
    except Exception:
        pass


def _upload_status_from_candidate_counts(counts: Counter) -> str:
    if not counts:
        return "NEW"
    if counts.get("PENDING"):
        return "PARSED"
    return "REVIEWED"


def sync_upload_review_status(raw_upload: RawKBUpload) -> RawKBUpload:
    counts = Counter(raw_upload.candidates.values_list("status", flat=True))
    next_status = _upload_status_from_candidate_counts(counts)
    if raw_upload.status != next_status:
        raw_upload.status = next_status
        raw_upload.save(update_fields=["status", "updated_at"])
    return raw_upload


@transaction.atomic
def replace_candidate_entity(candidate: CandidateEntity, payload: Dict[str, Any]) -> CandidateEntity:
    current = dict(candidate.payload or {})
    incoming = dict(payload or {})

    if "entity_key" in incoming:
        current["entity_key"] = incoming.get("entity_key")
    if "canonical_key" in incoming:
        current["canonical_key"] = incoming.get("canonical_key")
    if "category" in incoming:
        current["category"] = incoming.get("category")
    if "source" in incoming:
        current["source"] = incoming.get("source")
    if "langs" in incoming:
        current["langs"] = incoming.get("langs")

    # 候选编辑阶段直接保存当前编辑后的内容，不再强制做术语过滤或格式收紧，
    # 以便管理员可以先保存草稿，再逐步整理。
    candidate.payload = current
    candidate.save(update_fields=["payload", "updated_at"])
    return candidate


@transaction.atomic
def approve_candidate_entity(
    candidate: CandidateEntity,
    *,
    reviewed_by=None,
    review_notes: str = "",
) -> Tuple[CandidateEntity, KBEntity, bool]:
    fallback_source = candidate.raw_upload.file.name if candidate.raw_upload.file else f"upload_{candidate.raw_upload_id}"
    payload = sanitize_candidate_payload(candidate.payload or {}, fallback_source=fallback_source)
    # 允许管理员直接把任意上传内容整理成正式知识条目，不再强制要求必须先有术语名
    entity, created = upsert_kb_entity(payload)

    candidate.payload = payload
    candidate.status = "APPROVED"
    candidate.review_notes = review_notes
    candidate.approved_entity = entity
    candidate.reviewed_by = reviewed_by
    candidate.reviewed_at = timezone.now()
    candidate.save(
        update_fields=[
            "payload",
            "status",
            "review_notes",
            "approved_entity",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )
    sync_upload_review_status(candidate.raw_upload)
    return candidate, entity, created


@transaction.atomic
def reject_candidate_entity(
    candidate: CandidateEntity,
    *,
    reviewed_by=None,
    review_notes: str = "",
) -> CandidateEntity:
    candidate.status = "REJECTED"
    candidate.review_notes = review_notes
    candidate.reviewed_by = reviewed_by
    candidate.reviewed_at = timezone.now()
    candidate.save(
        update_fields=[
            "status",
            "review_notes",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )
    sync_upload_review_status(candidate.raw_upload)
    return candidate
