import os
import sys
import json
import glob
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

import numpy as np
import faiss

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
APPS_DIR = BACKEND_DIR / "apps"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(APPS_DIR))

# 你原来用的是 config.settings / backend.settings 之一，这里做双保险
if "DJANGO_SETTINGS_MODULE" not in os.environ:
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

import django  # noqa: E402

try:
    django.setup()
except Exception:
    # 允许纯文件模式运行
    pass

try:
    from django.apps import apps
except Exception:
    apps = None

from backend.core.embeddings.embedder import embed_texts  # noqa: E402

KB_DIR = ROOT / "backend" / "data" / "kb"
RAW_DIR = ROOT / "backend" / "data" / "kb_raw"
INDEX_PATH = KB_DIR / "faiss.index"
META_PATH = KB_DIR / "meta.json"          # 兼容现有 kb.py
ENTITIES_PATH = KB_DIR / "entities.json"
TERM_INDEX_PATH = KB_DIR / "term_index.json"
CHUNKS_PATH = KB_DIR / "chunks.json"

LANG_CODE_MAP = {
    "zh": "zho_Hans",
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "ja": "jpn_Jpan",
}

SUPPORTED_LANGS = set(LANG_CODE_MAP.keys())

FIELD_KEYS = {
    "id",
    "canonical_key",
    "category",
    "source",
    "term",
    "aliases",
    "definition",
    "symptoms",
    "causes",
    "diagnosis",
    "treatment",
    "prevention",
    "notes",
}

TEXT_FIELDS = ["definition", "symptoms", "causes", "diagnosis", "treatment", "prevention", "notes"]

MAX_EMBED_CHARS = 1200
DEFAULT_CATEGORY = "disease"
DEFAULT_SOURCE = "manual"


def read_text_file(fp: Path) -> str:
    return fp.read_text(encoding="utf-8", errors="ignore")


def _norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _norm_en(s: str) -> str:
    s = _norm_spaces(s).lower()
    s = s.strip(" .,:;()[]{}\"'“”‘’")
    return s


def slugify_key(s: str) -> str:
    s = _norm_en(s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "kb_item"


def safe_text(s: str, max_chars: int = MAX_EMBED_CHARS) -> str:
    s = (s or "").strip()
    if len(s) > max_chars:
        return s[:max_chars]
    return s


def detect_lang(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return "zh"

    # 日文：假名优先
    if re.search(r"[ぁ-んァ-ン]", s):
        return "ja"

    # 法语
    if re.search(r"[éèêëàâîïôùûüçÉÈÊËÀÂÎÏÔÙÛÜÇ]", s):
        return "fr"

    # 德语
    if re.search(r"[äöüßÄÖÜ]", s):
        return "de"

    # 中文
    if re.search(r"[\u4e00-\u9fff]", s) and not re.search(r"[A-Za-z]", s):
        return "zh"

    # 英文/拉丁字母兜底
    if re.search(r"[A-Za-z]", s):
        return "en"

    return "zh"


def parse_aliases(value: str) -> List[str]:
    raw = (value or "").strip()
    if not raw:
        return []

    parts = re.split(r"[;,；，、|/]+", raw)
    out = []
    seen = set()
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def parse_key_value_lines(block_text: str) -> Dict[str, Any]:
    """
    一行一行解析，避免 definition/symptoms 贪婪吞后续所有内容。
    """
    result: Dict[str, Any] = {}
    for raw_line in (block_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key not in FIELD_KEYS:
            continue

        if key == "aliases":
            result[key] = parse_aliases(value)
        else:
            result[key] = value

    return result


def split_entity_blocks(raw_text: str) -> List[str]:
    """
    按 [ENTITY] 严格切分。
    """
    parts = re.split(r"(?m)^\[ENTITY\]\s*$", raw_text or "")
    return [p.strip() for p in parts if p.strip()]


def split_lang_blocks(entity_block: str) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """
    返回:
    - entity_meta: id / canonical_key / category / source
    - lang_payloads: {lang: {...}}
    """
    lang_parts = re.split(r"(?m)^\[LANG:([a-z]{2})\]\s*$", entity_block or "")

    # lang_parts[0] 是 entity 级头部
    head_text = lang_parts[0].strip() if lang_parts else ""
    entity_meta = parse_key_value_lines(head_text)

    lang_payloads: Dict[str, Dict[str, Any]] = {}

    i = 1
    while i + 1 < len(lang_parts):
        lang = (lang_parts[i] or "").strip().lower()
        payload_text = lang_parts[i + 1] or ""
        i += 2

        if lang not in SUPPORTED_LANGS:
            continue

        payload = parse_key_value_lines(payload_text)
        if payload:
            lang_payloads[lang] = payload

    return entity_meta, lang_payloads


def build_entity_from_block(entity_block: str, source_name: str, ordinal: int) -> Optional[Dict[str, Any]]:
    entity_meta, lang_payloads = split_lang_blocks(entity_block)

    if not lang_payloads:
        return None

    canonical_key = (entity_meta.get("canonical_key") or "").strip()
    category = (entity_meta.get("category") or "").strip() or DEFAULT_CATEGORY
    source = (entity_meta.get("source") or "").strip() or source_name
    entity_id = (entity_meta.get("id") or "").strip()

    # 如果 canonical_key 缺失，优先从英文 term 推；否则从任意语言 term 推
    if not canonical_key:
        seed = ""
        if "en" in lang_payloads:
            seed = (lang_payloads["en"].get("term") or "").strip()
        if not seed:
            for lang in ["zh", "ja", "fr", "de", "en"]:
                if lang in lang_payloads:
                    seed = (lang_payloads[lang].get("term") or "").strip()
                    if seed:
                        break
        canonical_key = _norm_en(seed) or seed

    if not canonical_key:
        return None

    if not entity_id:
        entity_id = f"{category}_{slugify_key(canonical_key)}"

    entity = {
        "entity_id": entity_id,
        "canonical_key": canonical_key,
        "category": category,
        "source": source,
        "source_type": "file",
        "source_sections": [{"source": source_name, "section_id": ordinal}],
        "lang_terms": {},
        "lang_texts": {},
    }

    valid_lang_count = 0

    for lang, payload in lang_payloads.items():
        term = (payload.get("term") or "").strip()
        aliases = payload.get("aliases") or []
        if isinstance(aliases, str):
            aliases = parse_aliases(aliases)

        if term:
            entity["lang_terms"][lang] = {
                "name": term,
                "aliases": aliases,
            }
            valid_lang_count += 1

        entity["lang_texts"][lang] = {
            "definition": (payload.get("definition") or "").strip(),
            "symptoms": (payload.get("symptoms") or "").strip(),
            "diagnosis": (payload.get("diagnosis") or "").strip(),
            "treatment": (payload.get("treatment") or "").strip(),
            "notes": (payload.get("notes") or "").strip(),
        }

    if valid_lang_count == 0:
        return None

    return entity


def parse_raw_entities() -> List[Dict[str, Any]]:
    files = [Path(p) for p in glob.glob(str(RAW_DIR / "*.txt"))]
    files += [Path(p) for p in glob.glob(str(RAW_DIR / "*.md"))]

    entities: List[Dict[str, Any]] = []
    by_key: Dict[str, Dict[str, Any]] = {}

    for fp in files:
        raw = read_text_file(fp)
        entity_blocks = split_entity_blocks(raw)

        for idx, block in enumerate(entity_blocks):
            entity = build_entity_from_block(block, fp.name, idx)
            if not entity:
                continue

            ck = entity["canonical_key"]

            # 同 canonical_key 合并，避免不同文件重复
            if ck not in by_key:
                by_key[ck] = entity
                entities.append(entity)
                continue

            old = by_key[ck]

            # 合并基础信息
            old["category"] = old.get("category") or entity.get("category") or DEFAULT_CATEGORY
            old["source_sections"].extend(entity.get("source_sections", []))

            # 合并 lang_terms
            for lang, payload in entity.get("lang_terms", {}).items():
                if lang not in old["lang_terms"]:
                    old["lang_terms"][lang] = payload
                else:
                    old_payload = old["lang_terms"][lang]
                    old_name = (old_payload.get("name") or "").strip()
                    new_name = (payload.get("name") or "").strip()

                    if not old_name and new_name:
                        old_payload["name"] = new_name

                    old_aliases = list(old_payload.get("aliases") or [])
                    seen = set(old_aliases)
                    for x in payload.get("aliases", []) or []:
                        if x and x not in seen and x != old_payload.get("name"):
                            seen.add(x)
                            old_aliases.append(x)
                    old_payload["aliases"] = old_aliases

            # 合并 lang_texts：已有字段不覆盖，空字段补齐
            for lang, payload in entity.get("lang_texts", {}).items():
                old_bucket = old["lang_texts"].setdefault(lang, {
                    "definition": "",
                    "symptoms": "",
                    "diagnosis": "",
                    "treatment": "",
                    "notes": "",
                })
                for k, v in payload.items():
                    if v and not old_bucket.get(k):
                        old_bucket[k] = v

    return entities


def get_term_model():
    if apps is None:
        return None
    for app_label in ["terminology", "apps.terminology", "backend.apps.terminology"]:
        try:
            return apps.get_model(app_label, "Term")
        except LookupError:
            continue
    for m in apps.get_models():
        if m.__name__ == "Term" and "terminology" in (m.__module__ or ""):
            return m
    return None


def enrich_entities_from_terms(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    用数据库里的 Term 表补充中英文术语；不存在时不报错。
    """
    Term = get_term_model()
    if Term is None:
        return entities

    by_key = {e["canonical_key"]: e for e in entities}

    try:
        rows = Term.objects.all()
    except Exception:
        return entities

    for t in rows:
        term_en = (getattr(t, "term_en", "") or "").strip()
        term_zh = (getattr(t, "term_zh", "") or "").strip()
        category = (getattr(t, "category", "") or "").strip() or DEFAULT_CATEGORY
        source = (getattr(t, "source", "") or "").strip() or "TermTable"

        canonical_key = _norm_en(term_en) or term_zh
        if not canonical_key:
            continue

        if canonical_key not in by_key:
            entity = {
                "entity_id": f"{category}_{slugify_key(canonical_key)}",
                "canonical_key": canonical_key,
                "category": category,
                "source": source,
                "source_type": "terminology",
                "source_sections": [],
                "lang_terms": {},
                "lang_texts": {},
            }
            by_key[canonical_key] = entity
            entities.append(entity)

        entity = by_key[canonical_key]

        if term_zh:
            bucket = entity["lang_terms"].setdefault("zh", {"name": term_zh, "aliases": []})
            if not bucket.get("name"):
                bucket["name"] = term_zh
            elif term_zh != bucket["name"] and term_zh not in bucket["aliases"]:
                bucket["aliases"].append(term_zh)

        if term_en:
            bucket = entity["lang_terms"].setdefault("en", {"name": term_en, "aliases": []})
            if not bucket.get("name"):
                bucket["name"] = term_en
            elif term_en != bucket["name"] and term_en not in bucket["aliases"]:
                bucket["aliases"].append(term_en)

        if category and not entity.get("category"):
            entity["category"] = category

    return entities


def build_term_index(entities: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """
    term_index[lang][surface_form] = canonical_key
    """
    term_index = {lang: {} for lang in LANG_CODE_MAP.keys()}

    for e in entities:
        ck = (e.get("canonical_key") or "").strip()
        if not ck:
            continue

        for lang, payload in e.get("lang_terms", {}).items():
            if lang not in term_index:
                continue

            name = (payload.get("name") or "").strip()
            if name:
                term_index[lang][name] = ck

            for alias in payload.get("aliases", []) or []:
                alias = (alias or "").strip()
                if alias:
                    term_index[lang][alias] = ck

    return term_index


def build_full_text(lang: str, term: str, fields: Dict[str, str]) -> str:
    labels = {
        "zh": {
            "definition": "定义",
            "symptoms": "常见症状",
            "causes": "病因",
            "diagnosis": "诊断",
            "treatment": "治疗",
            "prevention": "预防",
            "notes": "注意",
        },
        "en": {
            "definition": "Definition",
            "symptoms": "Common symptoms",
            "causes": "Causes",
            "diagnosis": "Diagnosis",
            "treatment": "Treatment",
            "prevention": "Prevention",
            "notes": "Notes",
        },
        "fr": {
            "definition": "Définition",
            "symptoms": "Symptômes fréquents",
            "causes": "Causes",
            "diagnosis": "Diagnostic",
            "treatment": "Traitement",
            "prevention": "Prévention",
            "notes": "Précautions",
        },
        "de": {
            "definition": "Definition",
            "symptoms": "Häufige Symptome",
            "causes": "Ursachen",
            "diagnosis": "Diagnose",
            "treatment": "Behandlung",
            "prevention": "Prävention",
            "notes": "Hinweise",
        },
        "ja": {
            "definition": "定義",
            "symptoms": "主な症状",
            "causes": "原因",
            "diagnosis": "診断",
            "treatment": "治療",
            "prevention": "予防",
            "notes": "注意",
        },
    }.get(lang, {
        "definition": "Definition",
        "symptoms": "Symptoms",
        "causes": "Causes",
        "diagnosis": "Diagnosis",
        "treatment": "Treatment",
        "prevention": "Prevention",
        "notes": "Notes",
    })

    parts = [term]
    for field in TEXT_FIELDS:
        value = (fields.get(field) or "").strip()
        if value:
            parts.append(f"{labels[field]}: {value}")

    return "\n".join(parts).strip()


def build_chunks(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    chunks = []

    for e in entities:
        entity_id = e["entity_id"]
        canonical_key = e["canonical_key"]
        category = e.get("category") or DEFAULT_CATEGORY
        source = e.get("source") or DEFAULT_SOURCE
        source_type = e.get("source_type") or "file"

        for lang, term_info in e.get("lang_terms", {}).items():
            if lang not in SUPPORTED_LANGS:
                continue

            term = (term_info.get("name") or "").strip()
            if not term:
                continue

            aliases = term_info.get("aliases", []) or []
            fields = e.get("lang_texts", {}).get(lang, {}) or {}

            # 1) 术语块
            term_text = safe_text(
                f"Term: {term}\nCanonical: {canonical_key}\nCategory: {category}"
            )
            chunks.append({
                "chunk_id": f"{entity_id}_{lang}_term",
                "entity_id": entity_id,
                "canonical_key": canonical_key,
                "lang": lang,
                "lang_code": LANG_CODE_MAP.get(lang),
                "title": term,
                "term": term,
                "text_type": "term",
                "text": term_text,
                "aliases": aliases,
                "category": category,
                "source": source,
                "source_type": source_type,
            })

            # 2) 字段块
            for field_name in TEXT_FIELDS:
                value = (fields.get(field_name) or "").strip()
                if not value:
                    continue

                chunk_text = safe_text(f"{term}\n{field_name}: {value}")
                chunks.append({
                    "chunk_id": f"{entity_id}_{lang}_{field_name}",
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "lang": lang,
                    "lang_code": LANG_CODE_MAP.get(lang),
                    "title": term,
                    "term": term,
                    "text_type": field_name,
                    "text": chunk_text,
                    "aliases": aliases,
                    "category": category,
                    "source": source,
                    "source_type": source_type,
                })

            # 3) 全文块
            full_text = build_full_text(lang, term, fields)
            if full_text:
                chunks.append({
                    "chunk_id": f"{entity_id}_{lang}_full",
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "lang": lang,
                    "lang_code": LANG_CODE_MAP.get(lang),
                    "title": term,
                    "term": term,
                    "text_type": "full",
                    "text": safe_text(full_text),
                    "aliases": aliases,
                    "category": category,
                    "source": source,
                    "source_type": source_type,
                })

    return chunks


def build_legacy_meta_from_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    兼容现有 kb.py / FaissStore 的元数据格式。
    """
    legacy = []
    for c in chunks:
        legacy.append({
            "text": c.get("text", ""),
            "source_type": c.get("source_type", "file"),
            "source": c.get("source", DEFAULT_SOURCE),
            "title": c.get("title", ""),
            "term": c.get("term", ""),
            "lang": c.get("lang", "zh"),
            "lang_code": c.get("lang_code", ""),
            "category": c.get("category", DEFAULT_CATEGORY),
            "entity_id": c.get("entity_id", ""),
            "text_type": c.get("text_type", "full"),
            "chunk_id": c.get("chunk_id", ""),
            "canonical_key": c.get("canonical_key", ""),
            "aliases": c.get("aliases", []),
        })
    return legacy


def embed_chunks(chunks: List[Dict[str, Any]]) -> np.ndarray:
    texts = [c["text"] for c in chunks]
    embs = embed_texts(texts)
    embs = np.asarray(embs, dtype="float32")
    return embs


def save_outputs(
    entities: List[Dict[str, Any]],
    term_index: Dict[str, Dict[str, str]],
    chunks: List[Dict[str, Any]],
    legacy_meta: List[Dict[str, Any]],
    embs: np.ndarray,
):
    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embs)

    KB_DIR.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, str(INDEX_PATH))

    with open(ENTITIES_PATH, "w", encoding="utf-8") as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)

    with open(TERM_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(term_index, f, ensure_ascii=False, indent=2)

    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(legacy_meta, f, ensure_ascii=False, indent=2)


def validate_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    过滤明显坏掉的实体，避免把脏数据送进 embedding。
    """
    cleaned = []

    for e in entities:
        ck = (e.get("canonical_key") or "").strip()
        entity_id = (e.get("entity_id") or "").strip()
        lang_terms = e.get("lang_terms") or {}

        if not ck or not entity_id:
            continue

        valid_terms = 0
        for lang, payload in lang_terms.items():
            if lang not in SUPPORTED_LANGS:
                continue
            name = (payload.get("name") or "").strip()
            if name:
                valid_terms += 1

        if valid_terms == 0:
            continue

        cleaned.append(e)

    return cleaned


def print_summary(entities, chunks):
    print("Built multilingual KB successfully.")
    print("Entities:", len(entities))
    print("Chunks:", len(chunks))
    print("Index:", INDEX_PATH)
    print("Entities:", ENTITIES_PATH)
    print("Term index:", TERM_INDEX_PATH)
    print("Chunks meta:", CHUNKS_PATH)
    print("Legacy meta:", META_PATH)


def main():
    KB_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    entities = parse_raw_entities()

    generated_path = KB_DIR / "entities_generated.json"
    if generated_path.exists():
        try:
            generated = json.loads(generated_path.read_text(encoding="utf-8"))
            generated = [e for e in generated if isinstance(e, dict) and e.get("canonical_key")]
            existing_keys = {e.get("canonical_key", "") for e in entities}
            new_count = sum(1 for e in generated if e.get("canonical_key") not in existing_keys)
            entities.extend(e for e in generated if e.get("canonical_key") not in existing_keys)
            print(f"Merged {new_count} new entities from entities_generated.json (total: {len(generated)})")
        except Exception as e:
            print(f"Warning: Failed to merge entities_generated.json: {e}")
    entities = enrich_entities_from_terms(entities)
    entities = validate_entities(entities)

    term_index = build_term_index(entities)
    chunks = build_chunks(entities)
    legacy_meta = build_legacy_meta_from_chunks(chunks)

    if not entities:
        print("No valid entities found. Check backend/data/kb_raw/*.txt or *.md")
        return

    if not chunks:
        print("No valid chunks found after parsing entities.")
        return

    embs = embed_chunks(chunks)
    if embs.ndim != 2 or embs.shape[0] != len(chunks):
        raise RuntimeError(f"Embedding shape mismatch: {embs.shape}, chunks={len(chunks)}")

    save_outputs(
        entities=entities,
        term_index=term_index,
        chunks=chunks,
        legacy_meta=legacy_meta,
        embs=embs,
    )

    print_summary(entities, chunks)


if __name__ == "__main__":
    main()