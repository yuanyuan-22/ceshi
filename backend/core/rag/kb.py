# backend/core/rag/kb.py
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import re

import numpy as np

from backend.core.rag.faiss_store import FaissStore
from backend.core.embeddings.embedder import embed_texts


def _norm_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_en(s: str) -> str:
    s = _norm_text(s).lower()
    s = s.strip(" .,:;()[]{}\"'“”‘’")
    return s


def _concept_key(m: Dict[str, Any]) -> str:
    """
    新版概念键：
    1. canonical_key
    2. entity_id
    3. term/title
    """
    ck = (m.get("canonical_key") or "").strip()
    if ck:
        return ck

    eid = (m.get("entity_id") or "").strip()
    if eid:
        return eid

    term = _norm_en(m.get("term") or "")
    if term:
        return term

    title = _norm_en(m.get("title") or "")
    if title:
        return title

    return "KB Document"


def _text_quality_score(text: str) -> int:
    text = (text or "").strip()
    if not text:
        return -100

    score = 0
    if len(text) >= 24:
        score += 1
    if "\n" in text:
        score += 1
    if re.search(r"[。！？；：]", text):
        score += 1
    if re.search(r"[A-Za-z]{3,}", text):
        score += 1

    # Penalize obviously broken or repetitive fragments.
    if re.search(r"(.)\1{5,}", text):
        score -= 3
    if re.search(r"([.。,，!?！？;；:\-])(?:\s*\1){5,}", text):
        score -= 3
    if re.search(r"(?:\b\w{1,3}\b[\s,.;:!?-]*){8,}", text):
        score -= 1

    return score


def _lang_bonus(hit: Dict[str, Any], preferred_langs: Optional[List[str]] = None) -> int:
    if not preferred_langs:
        return 0

    lang = (hit.get("lang") or "").strip()
    if not lang:
        return 0

    try:
        rank = preferred_langs.index(lang)
    except ValueError:
        return 0

    return max(0, len(preferred_langs) - rank)


def _pick_better(
    a: Optional[Dict[str, Any]],
    b: Optional[Dict[str, Any]],
    preferred_langs: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    选择更好的候选
    优先级：
    1. score
    2. terminology 优先
    3. source=manual 优先
    4. full > definition/symptoms/... > term
    5. text 更长优先
    """
    if a is None:
        return b
    if b is None:
        return a

    sa = float(a.get("score", 0.0))
    sb = float(b.get("score", 0.0))
    if sb > sa + 1e-6:
        return b
    if sa > sb + 1e-6:
        return a

    ab = _lang_bonus(a, preferred_langs)
    bb = _lang_bonus(b, preferred_langs)
    if bb > ab:
        return b
    if ab > bb:
        return a

    a_term = (a.get("source_type") or "").strip() == "terminology"
    b_term = (b.get("source_type") or "").strip() == "terminology"
    if b_term and not a_term:
        return b
    if a_term and not b_term:
        return a

    am = (a.get("source") or "").lower() == "manual"
    bm = (b.get("source") or "").lower() == "manual"
    if bm and not am:
        return b
    if am and not bm:
        return a

    rank_map = {
        "full": 4,
        "definition": 3,
        "symptoms": 3,
        "diagnosis": 3,
        "treatment": 3,
        "notes": 3,
        "term": 1,
    }
    ra = rank_map.get((a.get("text_type") or "").strip(), 2)
    rb = rank_map.get((b.get("text_type") or "").strip(), 2)
    if rb > ra:
        return b
    if ra > rb:
        return a

    qa = _text_quality_score(a.get("text") or "")
    qb = _text_quality_score(b.get("text") or "")
    if qb > qa:
        return b
    if qa > qb:
        return a

    la = len((a.get("text") or ""))
    lb = len((b.get("text") or ""))
    return b if lb > la else a


class KB:
    """
    对外：kb.search(question: str, top_k: int) -> list[dict]
    内部：负责 embedding + faiss 检索 + meta 格式化 + 概念合并去重
    """

    def __init__(self, store: FaissStore, entities_path: Optional[Path] = None):
        self.store = store
        self.entities_by_key: Dict[str, Dict[str, Any]] = {}
        if entities_path and entities_path.exists():
            self._load_entities(entities_path)

    def _load_entities(self, entities_path: Path):
        try:
            data = json.loads(entities_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for e in data:
                    ck = (e.get("canonical_key") or "").strip()
                    if ck:
                        self.entities_by_key[ck] = e
        except Exception:
            self.entities_by_key = {}

    def _entity_terms(self, canonical_key: str) -> Dict[str, str]:
        e = self.entities_by_key.get(canonical_key) or {}
        lang_terms = e.get("lang_terms") or {}
        out = {}
        for lang, payload in lang_terms.items():
            name = (payload.get("name") or "").strip()
            if name:
                out[lang] = name
        return out

    def _format_hit(self, rank: int, idx: int, score: float) -> Dict[str, Any]:
        m = self.store.meta[idx]

        canonical_key = (m.get("canonical_key") or "").strip()
        entity_terms = self._entity_terms(canonical_key)

        term = (m.get("term") or "").strip()
        title = (m.get("title") or term or "KB Document").strip()

        term_zh = entity_terms.get("zh", "")
        term_en = entity_terms.get("en", "")
        term_fr = entity_terms.get("fr", "")
        term_de = entity_terms.get("de", "")
        term_ja = entity_terms.get("ja", "")

        lang = (m.get("lang") or "").strip()
        if not term:
            if lang and entity_terms.get(lang):
                term = entity_terms.get(lang, "")
            elif title:
                term = title

        return {
            "rank": rank,
            "doc_id": idx,
            "chunk_id": m.get("chunk_id", rank),
            "score": float(score),

            "title": title,
            "term": term,
            "text": m.get("text", ""),
            "source_type": m.get("source_type", ""),
            "source": m.get("source", ""),

            "lang": lang,
            "lang_code": m.get("lang_code", ""),
            "entity_id": m.get("entity_id", ""),
            "text_type": m.get("text_type", ""),
            "aliases": m.get("aliases", []),

            "term_zh": term_zh,
            "term_en": term_en,
            "term_fr": term_fr,
            "term_de": term_de,
            "term_ja": term_ja,

            "category": m.get("category", ""),
            "section_id": m.get("section_id", None),
            "canonical_key": canonical_key,
        }

    def search(
        self,
        question: str,
        top_k: int = 5,
        preferred_langs: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        q_emb = embed_texts([question])[0]
        q_emb = np.asarray(q_emb, dtype=np.float32)

        fetch_k = min(60, max(top_k * 6, top_k))
        ids_scores = self.store.search(q_emb, top_k=fetch_k)

        raw_hits: List[Dict[str, Any]] = []
        for rank, (idx, score) in enumerate(ids_scores):
            raw_hits.append(self._format_hit(rank, idx, score))

        grouped: Dict[str, Dict[str, Any]] = {}
        for h in raw_hits:
            ck = _concept_key(h)
            g = grouped.setdefault(
                ck,
                {
                    "concept_key": ck,
                    "head": None,        # terminology / term
                    "explain": None,     # file / full / field text
                    "best_score": 0.0,
                    "source_types": set(),
                    "langs": set(),
                },
            )

            g["best_score"] = max(g["best_score"], float(h.get("score", 0.0)))
            st = (h.get("source_type") or "").strip()
            if st:
                g["source_types"].add(st)

            lang = (h.get("lang") or "").strip()
            if lang:
                g["langs"].add(lang)

            text_type = (h.get("text_type") or "").strip()
            if st == "terminology" or text_type == "term":
                g["head"] = _pick_better(g["head"], h, preferred_langs=preferred_langs)
            else:
                g["explain"] = _pick_better(g["explain"], h, preferred_langs=preferred_langs)

        merged: List[Dict[str, Any]] = []
        for ck, g in grouped.items():
            head = g["head"]
            explain = g["explain"]

            if head is not None:
                out = dict(head)
            elif explain is not None:
                out = dict(explain)
            else:
                continue

            out["concept_key"] = ck
            out["group_source_types"] = sorted([x for x in g["source_types"] if x])
            out["best_score"] = float(g["best_score"])
            out["group_langs"] = sorted([x for x in g["langs"] if x])

            out["head_text"] = (head.get("text") if head else "") or ""
            out["head_source"] = (head.get("source") if head else "") or ""
            out["head_source_type"] = (head.get("source_type") if head else "") or ""
            out["head_lang"] = (head.get("lang") if head else "") or ""
            out["head_text_type"] = (head.get("text_type") if head else "") or ""

            out["explain_text"] = (explain.get("text") if explain else "") or ""
            out["explain_source"] = (explain.get("source") if explain else "") or ""
            out["explain_source_type"] = (explain.get("source_type") if explain else "") or ""
            out["explain_lang"] = (explain.get("lang") if explain else "") or ""
            out["explain_text_type"] = (explain.get("text_type") if explain else "") or ""

            if out.get("term_zh"):
                out["title"] = out["term_zh"]
            elif out.get("title"):
                out["title"] = out["title"]
            elif explain and explain.get("title"):
                out["title"] = explain.get("title")
            elif out.get("term"):
                out["title"] = out["term"]

            merged.append(out)

        # Second dedup pass: merge entities with identical Chinese names (term_zh)
        zh_name_groups: Dict[str, List[Dict[str, Any]]] = {}
        for item in merged:
            zh_name = (item.get("term_zh") or "").strip()
            if zh_name:
                zh_name_groups.setdefault(zh_name, []).append(item)
        deduped: List[Dict[str, Any]] = []
        seen_second = set()
        for item in merged:
            zh_name = (item.get("term_zh") or "").strip()
            if zh_name in zh_name_groups and len(zh_name_groups[zh_name]) > 1:
                if zh_name not in seen_second:
                    seen_second.add(zh_name)
                    best = max(zh_name_groups[zh_name],
                               key=lambda x: float(x.get("best_score", x.get("score", 0.0))))
                    deduped.append(best)
            else:
                deduped.append(item)

        deduped.sort(key=lambda x: float(x.get("best_score", x.get("score", 0.0))), reverse=True)
        return deduped[:top_k]


_KB_CACHE = None


def get_kb() -> KB:
    global _KB_CACHE
    if _KB_CACHE is not None:
        return _KB_CACHE

    backend_dir = Path(__file__).resolve().parents[2]  # .../backend
    kb_dir = backend_dir / "data" / "kb"
    index_path = str(kb_dir / "faiss.index")
    meta_path = str(kb_dir / "meta.json")
    entities_path = kb_dir / "entities.json"

    store = FaissStore(index_path=index_path, meta_path=meta_path)
    store.load()

    _KB_CACHE = KB(store=store, entities_path=entities_path)
    return _KB_CACHE
