# -*- coding: utf-8 -*-
"""
从现有医学知识库（entities.json / chunks.json / term_index.json）生成 NLLB 微调数据。
输出：
1. train_nllb_all.jsonl        全量样本
2. train_nllb_train.jsonl      训练集
3. train_nllb_val.jsonl        验证集
4. train_nllb_test.jsonl       测试集
5. term_eval_pairs.jsonl       术语评测集
6. data_stats.json             数据统计



升级版输出：
1. train_nllb_all.jsonl
2. train_nllb_train.jsonl
3. train_nllb_val.jsonl
4. train_nllb_test.jsonl
5. term_eval_pairs.jsonl
6. sentence_eval_pairs.jsonl
7. data_stats.json

样本格式：
{
  "src_text": "患者患有高血压。",
  "tgt_text": "The patient has hypertension.",
  "src_lang": "zho_Hans",
  "tgt_lang": "eng_Latn",
  "sample_type": "term|alias_term|term_normalization|field_text|field_sentence|full_text|template|sentence_template",
  "entity_id": "disease_hypertension",
  "canonical_key": "hypertension",
  "category": "disease",
  "text_field": "term|definition|symptoms|diagnosis|treatment|notes|full|template|sentence_template",
  "meta": {...}
}
Windows
python .\scripts\generate_nllb_medical_data.py `
  --entities ".\backend\data\kb\entities.json" `
  --output_dir ".\backend\data\nllb" `
  --seed 42 `
  --train_ratio 0.8 `
  --val_ratio 0.1 `
  --max_pairs_per_category 50

linux
python scripts/generate_nllb_medical_data.py \
  --entities "backend/data/kb/entities.json" \
  --output_dir "backend/data/nllb" \
  --seed 42 \
  --train_ratio 0.8 \
  --val_ratio 0.1 \
  --max_pairs_per_category 50


"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


LANG_TO_NLLB = {
    "zh": "zho_Hans",
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "ja": "jpn_Jpan",
}

TEXT_FIELDS = ["definition", "symptoms", "diagnosis", "treatment", "notes"]

# 单术语模板：保留你旧版已有能力
TEMPLATE_PAIRS = {
    ("zh", "en"): [
        ("患者患有{src_term}。", "The patient has {tgt_term}."),
        ("考虑诊断为{src_term}。", "{tgt_term} is considered."),
        ("既往有{src_term}病史。", "There is a history of {tgt_term}."),
        ("建议进一步评估{src_term}。", "Further evaluation for {tgt_term} is recommended."),
    ],
    ("en", "zh"): [
        ("The patient has {src_term}.", "患者患有{tgt_term}。"),
        ("{src_term} is considered.", "考虑诊断为{tgt_term}。"),
        ("There is a history of {src_term}.", "既往有{tgt_term}病史。"),
        ("Further evaluation for {src_term} is recommended.", "建议进一步评估{tgt_term}。"),
    ],
}

# 新增：更贴近实际输入的句级模板
SENTENCE_TEMPLATE_PAIRS = {
    ("zh", "en"): [
        ("患者患有{src_term}。", "The patient has {tgt_term}."),
        ("该患者既往有{src_term}病史。", "The patient has a history of {tgt_term}."),
        ("考虑{src_term}可能。", "{tgt_term} is suspected."),
        ("建议监测{src_hint}并规律服药。", "Monitoring of {tgt_hint} and regular medication are recommended."),
        ("建议进一步检查以明确是否存在{src_term}。", "Further examination is recommended to determine whether {tgt_term} is present."),
    ],
    ("en", "zh"): [
        ("The patient has {src_term}.", "患者患有{tgt_term}。"),
        ("The patient has a history of {src_term}.", "该患者既往有{tgt_term}病史。"),
        ("{src_term} is suspected.", "考虑{tgt_term}可能。"),
        ("Monitoring of {src_hint} and regular medication are recommended.", "建议监测{tgt_hint}并规律服药。"),
        ("Further examination is recommended to determine whether {src_term} is present.", "建议进一步检查以明确是否存在{tgt_term}。"),
    ],
}

# 新增：并列术语模板
PAIR_SENTENCE_TEMPLATE_PAIRS = {
    ("zh", "en"): [
        ("患者患有{src_term1}和{src_term2}。", "The patient has {tgt_term1} and {tgt_term2}."),
        ("既往病史包括{src_term1}和{src_term2}。", "The medical history includes {tgt_term1} and {tgt_term2}."),
        ("考虑患者合并{src_term1}及{src_term2}。", "The patient is considered to have {tgt_term1} and {tgt_term2}."),
    ],
    ("en", "zh"): [
        ("The patient has {src_term1} and {src_term2}.", "患者患有{tgt_term1}和{tgt_term2}。"),
        ("The medical history includes {src_term1} and {src_term2}.", "既往病史包括{tgt_term1}和{tgt_term2}。"),
        ("The patient is considered to have {src_term1} and {src_term2}.", "考虑患者合并{tgt_term1}及{tgt_term2}。"),
    ],
}

# 一些常见的术语规范化映射 hint
ZH_HINT_BY_CATEGORY = {
    "disease": "相关指标",
    "symptom": "相关症状",
    "examination": "检查指标",
    "test": "检查指标",
    "drug": "用药情况",
    "treatment": "治疗情况",
}
EN_HINT_BY_CATEGORY = {
    "disease": "relevant indicators",
    "symptom": "related symptoms",
    "examination": "examination indicators",
    "test": "examination indicators",
    "drug": "medication use",
    "treatment": "treatment status",
}


def normalize_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def split_dataset(
    samples: List[Dict[str, Any]],
    seed: int,
    train_ratio: float,
    val_ratio: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    rnd = random.Random(seed)
    items = samples[:]
    rnd.shuffle(items)

    total = len(items)
    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)
    train_data = items[:train_end]
    val_data = items[train_end:val_end]
    test_data = items[val_end:]
    return train_data, val_data, test_data


def split_sentences(text: str, lang: str) -> List[str]:
    text = normalize_text(text)
    if not text:
        return []

    if lang == "zh":
        parts = re.split(r"[。；;！？!?]\s*", text)
    else:
        parts = re.split(r"(?<=[\.\!\?;])\s+", text)

    results = []
    for p in parts:
        p = normalize_text(p)
        if not p:
            continue
        if len(p) < 3:
            continue
        results.append(p)
    return results


def ensure_sentence_end(text: str, lang: str) -> str:
    text = normalize_text(text)
    if not text:
        return text

    if lang == "zh":
        if text[-1] not in "。！？":
            text += "。"
    else:
        if text[-1] not in ".!?":
            text += "."
    return text


def sample_key(sample: Dict[str, Any]) -> str:
    return "|||".join([
        sample["src_lang"],
        sample["tgt_lang"],
        sample["sample_type"],
        normalize_text(sample["src_text"]),
        normalize_text(sample["tgt_text"]),
    ])


def add_sample(bucket: List[Dict[str, Any]], sample: Dict[str, Any], dedup: set[str]) -> bool:
    src = normalize_text(sample["src_text"])
    tgt = normalize_text(sample["tgt_text"])
    if not src or not tgt or src == tgt:
        return False

    sample["src_text"] = src
    sample["tgt_text"] = tgt
    key = sample_key(sample)
    if key in dedup:
        return False
    dedup.add(key)
    bucket.append(sample)
    return True


def add_eval_pair(bucket: List[Dict[str, Any]], row: Dict[str, Any], dedup: set[str]) -> bool:
    src = normalize_text(row["src_text"])
    tgt = normalize_text(row["tgt_text"])
    if not src or not tgt:
        return False

    key = "|||".join([row["src_lang"], row["tgt_lang"], src, tgt, row.get("eval_type", "")])
    if key in dedup:
        return False
    dedup.add(key)

    row["src_text"] = src
    row["tgt_text"] = tgt
    bucket.append(row)
    return True


def load_existing_rows(
    output_dir: Path,
    sample_bucket: List[Dict[str, Any]],
    term_eval_bucket: List[Dict[str, Any]],
    sentence_eval_bucket: List[Dict[str, Any]],
    sample_dedup: set[str],
    term_eval_dedup: set[str],
    sentence_eval_dedup: set[str],
) -> Dict[str, int]:
    existing_samples = read_jsonl(output_dir / "train_nllb_all.jsonl")
    if not existing_samples:
        # Fallback to train/val/test if all-file is absent.
        existing_samples = (
            read_jsonl(output_dir / "train_nllb_train.jsonl")
            + read_jsonl(output_dir / "train_nllb_val.jsonl")
            + read_jsonl(output_dir / "train_nllb_test.jsonl")
        )
    existing_term_eval = read_jsonl(output_dir / "term_eval_pairs.jsonl")
    existing_sentence_eval = read_jsonl(output_dir / "sentence_eval_pairs.jsonl")

    sample_added = 0
    for row in existing_samples:
        try:
            if add_sample(sample_bucket, row, sample_dedup):
                sample_added += 1
        except KeyError:
            continue

    term_eval_added = 0
    for row in existing_term_eval:
        try:
            if add_eval_pair(term_eval_bucket, row, term_eval_dedup):
                term_eval_added += 1
        except KeyError:
            continue

    sentence_eval_added = 0
    for row in existing_sentence_eval:
        try:
            if add_eval_pair(sentence_eval_bucket, row, sentence_eval_dedup):
                sentence_eval_added += 1
        except KeyError:
            continue

    return {
        "existing_samples_raw": len(existing_samples),
        "existing_samples_loaded": sample_added,
        "existing_term_eval_raw": len(existing_term_eval),
        "existing_term_eval_loaded": term_eval_added,
        "existing_sentence_eval_raw": len(existing_sentence_eval),
        "existing_sentence_eval_loaded": sentence_eval_added,
    }


def get_lang_name(lang_terms: Dict[str, Any], lang: str) -> str:
    return normalize_text((lang_terms.get(lang) or {}).get("name", ""))


def get_lang_aliases(lang_terms: Dict[str, Any], lang: str) -> List[str]:
    aliases = (lang_terms.get(lang) or {}).get("aliases", []) or []
    return [normalize_text(x) for x in aliases if normalize_text(x)]


def get_hint_by_category(category: str, lang: str) -> str:
    if lang == "zh":
        return ZH_HINT_BY_CATEGORY.get(category or "", "相关指标")
    return EN_HINT_BY_CATEGORY.get(category or "", "relevant indicators")


def build_term_samples(
    entity: Dict[str, Any],
    sample_list: List[Dict[str, Any]],
    term_eval: List[Dict[str, Any]],
    sample_dedup: set[str],
    term_eval_dedup: set[str],
) -> None:
    entity_id = entity.get("entity_id")
    canonical_key = entity.get("canonical_key")
    category = entity.get("category")
    lang_terms = entity.get("lang_terms") or {}

    available_langs = [lang for lang in LANG_TO_NLLB if get_lang_name(lang_terms, lang)]

    for src_lang in available_langs:
        src_name = get_lang_name(lang_terms, src_lang)
        src_aliases = get_lang_aliases(lang_terms, src_lang)

        for tgt_lang in available_langs:
            if src_lang == tgt_lang:
                continue

            tgt_name = get_lang_name(lang_terms, tgt_lang)
            if not tgt_name:
                continue

            # 1) canonical term -> canonical term
            add_sample(sample_list, {
                "src_text": src_name,
                "tgt_text": tgt_name,
                "src_lang": LANG_TO_NLLB[src_lang],
                "tgt_lang": LANG_TO_NLLB[tgt_lang],
                "sample_type": "term",
                "entity_id": entity_id,
                "canonical_key": canonical_key,
                "category": category,
                "text_field": "term",
                "meta": {
                    "src_lang": src_lang,
                    "tgt_lang": tgt_lang,
                    "src_is_alias": False,
                    "target_is_canonical_name": True,
                },
            }, sample_dedup)

            add_eval_pair(term_eval, {
                "src_text": src_name,
                "tgt_text": tgt_name,
                "src_lang": LANG_TO_NLLB[src_lang],
                "tgt_lang": LANG_TO_NLLB[tgt_lang],
                "entity_id": entity_id,
                "canonical_key": canonical_key,
                "category": category,
                "eval_type": "term",
            }, term_eval_dedup)

            # 2) alias -> canonical
            for alias in src_aliases:
                add_sample(sample_list, {
                    "src_text": alias,
                    "tgt_text": tgt_name,
                    "src_lang": LANG_TO_NLLB[src_lang],
                    "tgt_lang": LANG_TO_NLLB[tgt_lang],
                    "sample_type": "alias_term",
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "category": category,
                    "text_field": "term",
                    "meta": {
                        "src_lang": src_lang,
                        "tgt_lang": tgt_lang,
                        "src_is_alias": True,
                        "target_is_canonical_name": True,
                    },
                }, sample_dedup)


def build_term_normalization_samples(
    entity: Dict[str, Any],
    sample_list: List[Dict[str, Any]],
    sample_dedup: set[str],
) -> None:
    """
    显式强化：
    通俗/别名 -> 规范医学术语
    例如：
    High blood pressure -> Hypertension
    Diabetes -> Diabetes mellitus
    Asthma -> Bronchial asthma
    """
    entity_id = entity.get("entity_id")
    canonical_key = entity.get("canonical_key")
    category = entity.get("category")
    lang_terms = entity.get("lang_terms") or {}

    for lang in ("zh", "en"):
        canonical_name = get_lang_name(lang_terms, lang)
        aliases = get_lang_aliases(lang_terms, lang)
        if not canonical_name:
            continue

        for alias in aliases:
            if alias == canonical_name:
                continue

            add_sample(sample_list, {
                "src_text": alias,
                "tgt_text": canonical_name,
                "src_lang": LANG_TO_NLLB[lang],
                "tgt_lang": LANG_TO_NLLB[lang],
                "sample_type": "term_normalization",
                "entity_id": entity_id,
                "canonical_key": canonical_key,
                "category": category,
                "text_field": "term",
                "meta": {
                    "lang": lang,
                    "normalization": True,
                    "src_is_alias": True,
                    "target_is_canonical_name": True,
                },
            }, sample_dedup)

            # alias 放进句子里再做同语种规范化
            if lang == "en":
                add_sample(sample_list, {
                    "src_text": f"The patient has {alias}.",
                    "tgt_text": f"The patient has {canonical_name}.",
                    "src_lang": LANG_TO_NLLB[lang],
                    "tgt_lang": LANG_TO_NLLB[lang],
                    "sample_type": "term_normalization",
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "category": category,
                    "text_field": "template",
                    "meta": {
                        "lang": lang,
                        "normalization": True,
                        "in_sentence": True,
                    },
                }, sample_dedup)
            else:
                add_sample(sample_list, {
                    "src_text": f"患者患有{alias}。",
                    "tgt_text": f"患者患有{canonical_name}。",
                    "src_lang": LANG_TO_NLLB[lang],
                    "tgt_lang": LANG_TO_NLLB[lang],
                    "sample_type": "term_normalization",
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "category": category,
                    "text_field": "template",
                    "meta": {
                        "lang": lang,
                        "normalization": True,
                        "in_sentence": True,
                    },
                }, sample_dedup)


def build_field_text_samples(
    entity: Dict[str, Any],
    sample_list: List[Dict[str, Any]],
    sample_dedup: set[str],
) -> None:
    entity_id = entity.get("entity_id")
    canonical_key = entity.get("canonical_key")
    category = entity.get("category")
    lang_terms = entity.get("lang_terms") or {}
    lang_texts = entity.get("lang_texts") or {}

    available_langs = [
        lang for lang in LANG_TO_NLLB
        if lang in lang_texts and get_lang_name(lang_terms, lang)
    ]

    for src_lang in available_langs:
        for tgt_lang in available_langs:
            if src_lang == tgt_lang:
                continue

            src_text_block = lang_texts.get(src_lang) or {}
            tgt_text_block = lang_texts.get(tgt_lang) or {}

            for field in TEXT_FIELDS:
                src_text = normalize_text(src_text_block.get(field, ""))
                tgt_text = normalize_text(tgt_text_block.get(field, ""))
                if not src_text or not tgt_text:
                    continue

                # 整字段样本
                add_sample(sample_list, {
                    "src_text": src_text,
                    "tgt_text": tgt_text,
                    "src_lang": LANG_TO_NLLB[src_lang],
                    "tgt_lang": LANG_TO_NLLB[tgt_lang],
                    "sample_type": "field_text",
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "category": category,
                    "text_field": field,
                    "meta": {
                        "src_lang": src_lang,
                        "tgt_lang": tgt_lang,
                        "granularity": "field",
                    },
                }, sample_dedup)

                # 短句切分样本
                src_sentences = split_sentences(src_text, src_lang)
                tgt_sentences = split_sentences(tgt_text, tgt_lang)
                if src_sentences and tgt_sentences:
                    n = min(len(src_sentences), len(tgt_sentences))
                    for i in range(n):
                        s_src = ensure_sentence_end(src_sentences[i], src_lang)
                        s_tgt = ensure_sentence_end(tgt_sentences[i], tgt_lang)
                        add_sample(sample_list, {
                            "src_text": s_src,
                            "tgt_text": s_tgt,
                            "src_lang": LANG_TO_NLLB[src_lang],
                            "tgt_lang": LANG_TO_NLLB[tgt_lang],
                            "sample_type": "field_sentence",
                            "entity_id": entity_id,
                            "canonical_key": canonical_key,
                            "category": category,
                            "text_field": field,
                            "meta": {
                                "src_lang": src_lang,
                                "tgt_lang": tgt_lang,
                                "granularity": "sentence",
                                "sentence_index": i,
                            },
                        }, sample_dedup)


def build_full_text_samples(
    entity: Dict[str, Any],
    sample_list: List[Dict[str, Any]],
    sample_dedup: set[str],
) -> None:
    entity_id = entity.get("entity_id")
    canonical_key = entity.get("canonical_key")
    category = entity.get("category")
    lang_texts = entity.get("lang_texts") or {}
    lang_terms = entity.get("lang_terms") or {}

    available_langs = [
        lang for lang in LANG_TO_NLLB
        if lang in lang_texts and get_lang_name(lang_terms, lang)
    ]

    for src_lang in available_langs:
        for tgt_lang in available_langs:
            if src_lang == tgt_lang:
                continue

            src_parts = []
            tgt_parts = []
            for field in TEXT_FIELDS:
                src_text = normalize_text((lang_texts.get(src_lang) or {}).get(field, ""))
                tgt_text = normalize_text((lang_texts.get(tgt_lang) or {}).get(field, ""))
                if src_text and tgt_text:
                    src_parts.append(src_text)
                    tgt_parts.append(tgt_text)

            if len(src_parts) >= 2 and len(tgt_parts) >= 2:
                add_sample(sample_list, {
                    "src_text": " ".join(src_parts),
                    "tgt_text": " ".join(tgt_parts),
                    "src_lang": LANG_TO_NLLB[src_lang],
                    "tgt_lang": LANG_TO_NLLB[tgt_lang],
                    "sample_type": "full_text",
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "category": category,
                    "text_field": "full",
                    "meta": {
                        "src_lang": src_lang,
                        "tgt_lang": tgt_lang,
                    },
                }, sample_dedup)


def build_template_samples(
    entity: Dict[str, Any],
    sample_list: List[Dict[str, Any]],
    sentence_eval: List[Dict[str, Any]],
    sample_dedup: set[str],
    sentence_eval_dedup: set[str],
) -> None:
    """
    保留旧版单术语模板句
    """
    entity_id = entity.get("entity_id")
    canonical_key = entity.get("canonical_key")
    category = entity.get("category")
    lang_terms = entity.get("lang_terms") or {}

    if "zh" not in lang_terms or "en" not in lang_terms:
        return

    zh_name = get_lang_name(lang_terms, "zh")
    en_name = get_lang_name(lang_terms, "en")
    zh_aliases = get_lang_aliases(lang_terms, "zh")
    en_aliases = get_lang_aliases(lang_terms, "en")

    if not zh_name or not en_name:
        return

    src_candidates = [("zh", zh_name, False)] + [("zh", a, True) for a in zh_aliases]
    src_candidates += [("en", en_name, False)] + [("en", a, True) for a in en_aliases]

    for src_lang, src_term, src_is_alias in src_candidates:
        if src_lang == "zh":
            pair_key = ("zh", "en")
            tgt_term = en_name
        else:
            pair_key = ("en", "zh")
            tgt_term = zh_name

        for src_tpl, tgt_tpl in TEMPLATE_PAIRS[pair_key]:
            src_text = ensure_sentence_end(
                src_tpl.format(src_term=src_term, tgt_term=tgt_term),
                pair_key[0]
            )
            tgt_text = ensure_sentence_end(
                tgt_tpl.format(src_term=src_term, tgt_term=tgt_term),
                pair_key[1]
            )

            added = add_sample(sample_list, {
                "src_text": src_text,
                "tgt_text": tgt_text,
                "src_lang": LANG_TO_NLLB[pair_key[0]],
                "tgt_lang": LANG_TO_NLLB[pair_key[1]],
                "sample_type": "template",
                "entity_id": entity_id,
                "canonical_key": canonical_key,
                "category": category,
                "text_field": "template",
                "meta": {
                    "src_is_alias": src_is_alias,
                    "template_pair": f"{pair_key[0]}2{pair_key[1]}",
                },
            }, sample_dedup)

            if added:
                add_eval_pair(sentence_eval, {
                    "src_text": src_text,
                    "tgt_text": tgt_text,
                    "src_lang": LANG_TO_NLLB[pair_key[0]],
                    "tgt_lang": LANG_TO_NLLB[pair_key[1]],
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "category": category,
                    "eval_type": "template_sentence",
                }, sentence_eval_dedup)


def build_sentence_template_samples(
    entity: Dict[str, Any],
    sample_list: List[Dict[str, Any]],
    sentence_eval: List[Dict[str, Any]],
    sample_dedup: set[str],
    sentence_eval_dedup: set[str],
) -> None:
    """
    新增：
    1）更真实的单术语句
    2）会导出到 sentence_eval
    """
    entity_id = entity.get("entity_id")
    canonical_key = entity.get("canonical_key")
    category = entity.get("category")
    lang_terms = entity.get("lang_terms") or {}

    if "zh" not in lang_terms or "en" not in lang_terms:
        return

    zh_name = get_lang_name(lang_terms, "zh")
    en_name = get_lang_name(lang_terms, "en")
    zh_aliases = get_lang_aliases(lang_terms, "zh")
    en_aliases = get_lang_aliases(lang_terms, "en")

    if not zh_name or not en_name:
        return

    for pair_key in (("zh", "en"), ("en", "zh")):
        if pair_key[0] == "zh":
            src_name = zh_name
            tgt_name = en_name
            src_aliases = zh_aliases
        else:
            src_name = en_name
            tgt_name = zh_name
            src_aliases = en_aliases

        src_hint = get_hint_by_category(category, pair_key[0])
        tgt_hint = get_hint_by_category(category, pair_key[1])

        term_candidates = [(src_name, False)] + [(a, True) for a in src_aliases]

        for src_term, src_is_alias in term_candidates:
            for src_tpl, tgt_tpl in SENTENCE_TEMPLATE_PAIRS[pair_key]:
                src_text = ensure_sentence_end(
                    src_tpl.format(
                        src_term=src_term,
                        tgt_term=tgt_name,
                        src_hint=src_hint,
                        tgt_hint=tgt_hint,
                    ),
                    pair_key[0]
                )
                tgt_text = ensure_sentence_end(
                    tgt_tpl.format(
                        src_term=src_term,
                        tgt_term=tgt_name,
                        src_hint=src_hint,
                        tgt_hint=tgt_hint,
                    ),
                    pair_key[1]
                )

                added = add_sample(sample_list, {
                    "src_text": src_text,
                    "tgt_text": tgt_text,
                    "src_lang": LANG_TO_NLLB[pair_key[0]],
                    "tgt_lang": LANG_TO_NLLB[pair_key[1]],
                    "sample_type": "sentence_template",
                    "entity_id": entity_id,
                    "canonical_key": canonical_key,
                    "category": category,
                    "text_field": "sentence_template",
                    "meta": {
                        "src_is_alias": src_is_alias,
                        "template_pair": f"{pair_key[0]}2{pair_key[1]}",
                        "single_entity": True,
                    },
                }, sample_dedup)

                if added:
                    add_eval_pair(sentence_eval, {
                        "src_text": src_text,
                        "tgt_text": tgt_text,
                        "src_lang": LANG_TO_NLLB[pair_key[0]],
                        "tgt_lang": LANG_TO_NLLB[pair_key[1]],
                        "entity_id": entity_id,
                        "canonical_key": canonical_key,
                        "category": category,
                        "eval_type": "single_entity_sentence",
                    }, sentence_eval_dedup)


def build_pair_sentence_samples(
    entities: List[Dict[str, Any]],
    sample_list: List[Dict[str, Any]],
    sentence_eval: List[Dict[str, Any]],
    sample_dedup: set[str],
    sentence_eval_dedup: set[str],
    max_pairs_per_category: int = 50,
) -> None:
    """
    新增：
    生成并列术语句，重点解决：
    糖尿病和高血压 / 高血压和支气管哮喘 这种句子里术语不稳定的问题
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for e in entities:
        lang_terms = e.get("lang_terms") or {}
        zh_name = get_lang_name(lang_terms, "zh")
        en_name = get_lang_name(lang_terms, "en")
        category = e.get("category") or "unknown"

        if zh_name and en_name:
            grouped.setdefault(category, []).append(e)

    rnd = random.Random(42)

    for category, entity_group in grouped.items():
        pairs = list(combinations(entity_group, 2))
        rnd.shuffle(pairs)
        pairs = pairs[:max_pairs_per_category]

        for e1, e2 in pairs:
            e1_terms = e1.get("lang_terms") or {}
            e2_terms = e2.get("lang_terms") or {}

            zh1 = get_lang_name(e1_terms, "zh")
            zh2 = get_lang_name(e2_terms, "zh")
            en1 = get_lang_name(e1_terms, "en")
            en2 = get_lang_name(e2_terms, "en")
            if not all([zh1, zh2, en1, en2]):
                continue

            for pair_key in (("zh", "en"), ("en", "zh")):
                if pair_key[0] == "zh":
                    src_term1, src_term2 = zh1, zh2
                    tgt_term1, tgt_term2 = en1, en2
                else:
                    src_term1, src_term2 = en1, en2
                    tgt_term1, tgt_term2 = zh1, zh2

                for src_tpl, tgt_tpl in PAIR_SENTENCE_TEMPLATE_PAIRS[pair_key]:
                    src_text = ensure_sentence_end(
                        src_tpl.format(
                            src_term1=src_term1,
                            src_term2=src_term2,
                            tgt_term1=tgt_term1,
                            tgt_term2=tgt_term2,
                        ),
                        pair_key[0]
                    )
                    tgt_text = ensure_sentence_end(
                        tgt_tpl.format(
                            src_term1=src_term1,
                            src_term2=src_term2,
                            tgt_term1=tgt_term1,
                            tgt_term2=tgt_term2,
                        ),
                        pair_key[1]
                    )

                    added = add_sample(sample_list, {
                        "src_text": src_text,
                        "tgt_text": tgt_text,
                        "src_lang": LANG_TO_NLLB[pair_key[0]],
                        "tgt_lang": LANG_TO_NLLB[pair_key[1]],
                        "sample_type": "sentence_template",
                        "entity_id": f"{e1.get('entity_id')}__{e2.get('entity_id')}",
                        "canonical_key": f"{e1.get('canonical_key')}__{e2.get('canonical_key')}",
                        "category": category,
                        "text_field": "sentence_template",
                        "meta": {
                            "template_pair": f"{pair_key[0]}2{pair_key[1]}",
                            "multi_entity": True,
                            "entity_ids": [e1.get("entity_id"), e2.get("entity_id")],
                        },
                    }, sample_dedup)

                    if added:
                        add_eval_pair(sentence_eval, {
                            "src_text": src_text,
                            "tgt_text": tgt_text,
                            "src_lang": LANG_TO_NLLB[pair_key[0]],
                            "tgt_lang": LANG_TO_NLLB[pair_key[1]],
                            "entity_id": f"{e1.get('entity_id')}__{e2.get('entity_id')}",
                            "canonical_key": f"{e1.get('canonical_key')}__{e2.get('canonical_key')}",
                            "category": category,
                            "eval_type": "multi_entity_sentence",
                            "meta": {
                                "entity_ids": [e1.get("entity_id"), e2.get("entity_id")],
                            },
                        }, sentence_eval_dedup)


def entity_to_samples(
    entity: Dict[str, Any],
    sample_list: List[Dict[str, Any]],
    term_eval: List[Dict[str, Any]],
    sentence_eval: List[Dict[str, Any]],
    sample_dedup: set[str],
    term_eval_dedup: set[str],
    sentence_eval_dedup: set[str],
) -> None:
    build_term_samples(entity, sample_list, term_eval, sample_dedup, term_eval_dedup)
    build_term_normalization_samples(entity, sample_list, sample_dedup)
    build_field_text_samples(entity, sample_list, sample_dedup)
    build_full_text_samples(entity, sample_list, sample_dedup)
    build_template_samples(entity, sample_list, sentence_eval, sample_dedup, sentence_eval_dedup)
    build_sentence_template_samples(entity, sample_list, sentence_eval, sample_dedup, sentence_eval_dedup)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entities", type=str, required=True, help="entities.json 路径")
    parser.add_argument("--output_dir", type=str, required=True, help="输出目录")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train_ratio", type=float, default=0.8)
    parser.add_argument("--val_ratio", type=float, default=0.1)
    parser.add_argument(
        "--append",
        action="store_true",
        help="增量模式：先加载输出目录已有样本，再追加新样本并去重",
    )
    parser.add_argument(
        "--max_pairs_per_category",
        type=int,
        default=50,
        help="每个 category 最多生成多少组并列术语样本",
    )
    args = parser.parse_args()

    if args.train_ratio <= 0 or args.val_ratio <= 0 or args.train_ratio + args.val_ratio >= 1:
        raise ValueError("train_ratio 和 val_ratio 必须 > 0，且 train_ratio + val_ratio < 1")

    entities = load_json(Path(args.entities))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    samples: List[Dict[str, Any]] = []
    term_eval: List[Dict[str, Any]] = []
    sentence_eval: List[Dict[str, Any]] = []

    sample_dedup: set[str] = set()
    term_eval_dedup: set[str] = set()
    sentence_eval_dedup: set[str] = set()
    append_info = {
        "existing_samples_raw": 0,
        "existing_samples_loaded": 0,
        "existing_term_eval_raw": 0,
        "existing_term_eval_loaded": 0,
        "existing_sentence_eval_raw": 0,
        "existing_sentence_eval_loaded": 0,
    }

    if args.append:
        append_info = load_existing_rows(
            output_dir=output_dir,
            sample_bucket=samples,
            term_eval_bucket=term_eval,
            sentence_eval_bucket=sentence_eval,
            sample_dedup=sample_dedup,
            term_eval_dedup=term_eval_dedup,
            sentence_eval_dedup=sentence_eval_dedup,
        )

    for entity in entities:
        entity_to_samples(
            entity=entity,
            sample_list=samples,
            term_eval=term_eval,
            sentence_eval=sentence_eval,
            sample_dedup=sample_dedup,
            term_eval_dedup=term_eval_dedup,
            sentence_eval_dedup=sentence_eval_dedup,
        )

    # 新增：跨实体并列句
    build_pair_sentence_samples(
        entities=entities,
        sample_list=samples,
        sentence_eval=sentence_eval,
        sample_dedup=sample_dedup,
        sentence_eval_dedup=sentence_eval_dedup,
        max_pairs_per_category=args.max_pairs_per_category,
    )

    train_data, val_data, test_data = split_dataset(
        samples,
        seed=args.seed,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
    )

    write_jsonl(output_dir / "train_nllb_all.jsonl", samples)
    write_jsonl(output_dir / "train_nllb_train.jsonl", train_data)
    write_jsonl(output_dir / "train_nllb_val.jsonl", val_data)
    write_jsonl(output_dir / "train_nllb_test.jsonl", test_data)
    write_jsonl(output_dir / "term_eval_pairs.jsonl", term_eval)
    write_jsonl(output_dir / "sentence_eval_pairs.jsonl", sentence_eval)

    stats = {
        "num_entities": len(entities),
        "num_all_samples": len(samples),
        "num_train_samples": len(train_data),
        "num_val_samples": len(val_data),
        "num_test_samples": len(test_data),
        "num_term_eval_pairs": len(term_eval),
        "num_sentence_eval_pairs": len(sentence_eval),
        "sample_type_distribution": dict(Counter(x["sample_type"] for x in samples)),
        "language_pair_distribution": dict(Counter(f"{x['src_lang']}->{x['tgt_lang']}" for x in samples)),
        "text_field_distribution": dict(Counter(x["text_field"] for x in samples)),
        "eval_type_distribution": dict(Counter(x["eval_type"] for x in sentence_eval + term_eval)),
        "normalization_sample_count": sum(1 for x in samples if x["sample_type"] == "term_normalization"),
        "sentence_template_sample_count": sum(1 for x in samples if x["sample_type"] == "sentence_template"),
        "field_sentence_sample_count": sum(1 for x in samples if x["sample_type"] == "field_sentence"),
        "merge_mode": "append_dedup" if args.append else "overwrite",
        **append_info,
    }

    with (output_dir / "data_stats.json").open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"\nDone. Files written to: {output_dir}")


if __name__ == "__main__":
    main()
