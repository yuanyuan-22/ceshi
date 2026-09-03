from __future__ import annotations

import json
import os
import random
import re
import runpy
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = ROOT / "scripts" / "generate_nllb_medical_data.py"
BASE_NLLB_DIR = ROOT / "backend" / "data" / "nllb"
KB_DIR = ROOT / "backend" / "data" / "kb"
KB_ENTITIES = KB_DIR / "entities.json"
KB_ENTITIES_APP = KB_DIR / "kb_app_generated" / "entities.json"
KB_ENTITIES_DB_EXPORT = KB_DIR / "kb_app_generated" / "entities_db_export.json"
OUTPUT_DIR = ROOT / "backend" / "data" / "nllb" / "kb_app_generated"
SEED = 42
TRAIN_RATIO = 0.8
VAL_RATIO = 0.1

def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _sample_key(row: Dict[str, Any]) -> str:
    return "|||".join(
        [
            str(row.get("src_lang") or ""),
            str(row.get("tgt_lang") or ""),
            str(row.get("sample_type") or ""),
            _normalize_text(row.get("src_text")),
            _normalize_text(row.get("tgt_text")),
        ]
    )


def _eval_key(row: Dict[str, Any]) -> str:
    return "|||".join(
        [
            str(row.get("src_lang") or ""),
            str(row.get("tgt_lang") or ""),
            _normalize_text(row.get("src_text")),
            _normalize_text(row.get("tgt_text")),
            str(row.get("eval_type") or ""),
        ]
    )


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _dedupe_rows(rows: List[Dict[str, Any]], *, mode: str) -> List[Dict[str, Any]]:
    key_fn = _sample_key if mode == "sample" else _eval_key
    dedup: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        src = _normalize_text(row.get("src_text"))
        tgt = _normalize_text(row.get("tgt_text"))
        if not src or not tgt:
            continue
        if mode == "sample" and src == tgt:
            continue
        normalized = dict(row)
        normalized["src_text"] = src
        normalized["tgt_text"] = tgt
        dedup[key_fn(normalized)] = normalized
    return list(dedup.values())


def _load_sample_pool(directories: List[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for directory in directories:
        rows.extend(_read_jsonl(directory / "train_nllb_all.jsonl"))
        rows.extend(_read_jsonl(directory / "train_nllb_train.jsonl"))
        rows.extend(_read_jsonl(directory / "train_nllb_val.jsonl"))
        rows.extend(_read_jsonl(directory / "train_nllb_test.jsonl"))
    return _dedupe_rows(rows, mode="sample")


def _load_eval_pool(directories: List[Path], filename: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for directory in directories:
        rows.extend(_read_jsonl(directory / filename))
    return _dedupe_rows(rows, mode="eval")


def _split_dataset(samples: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    items = list(samples)
    rnd = random.Random(SEED)
    rnd.shuffle(items)

    total = len(items)
    train_end = int(total * TRAIN_RATIO)
    val_end = train_end + int(total * VAL_RATIO)
    return items[:train_end], items[train_end:val_end], items[val_end:]


def _compute_stats(
    samples_all: List[Dict[str, Any]],
    train_data: List[Dict[str, Any]],
    val_data: List[Dict[str, Any]],
    test_data: List[Dict[str, Any]],
    term_eval: List[Dict[str, Any]],
    sentence_eval: List[Dict[str, Any]],
) -> Dict[str, Any]:
    sample_types = Counter(str(x.get("sample_type") or "") for x in samples_all)
    lang_pairs = Counter(f"{x.get('src_lang')}->{x.get('tgt_lang')}" for x in samples_all)
    text_fields = Counter(str(x.get("text_field") or "") for x in samples_all)
    eval_types = Counter(str(x.get("eval_type") or "") for x in (term_eval + sentence_eval))

    return {
        "num_all_samples": len(samples_all),
        "num_train_samples": len(train_data),
        "num_val_samples": len(val_data),
        "num_test_samples": len(test_data),
        "num_term_eval_pairs": len(term_eval),
        "num_sentence_eval_pairs": len(sentence_eval),
        "sample_type_distribution": dict(sample_types),
        "language_pair_distribution": dict(lang_pairs),
        "text_field_distribution": dict(text_fields),
        "eval_type_distribution": dict(eval_types),
        "normalization_sample_count": sum(1 for x in samples_all if x.get("sample_type") == "term_normalization"),
        "sentence_template_sample_count": sum(1 for x in samples_all if x.get("sample_type") == "sentence_template"),
        "field_sentence_sample_count": sum(1 for x in samples_all if x.get("sample_type") == "field_sentence"),
    }


def _merge_incremental_outputs() -> Dict[str, Any]:
    # Keep a growing dataset: historical corpora + previous generated + newly generated.
    sources = [BASE_NLLB_DIR, OUTPUT_DIR]
    existing_samples = _load_sample_pool(sources)
    existing_term_eval = _load_eval_pool(sources, "term_eval_pairs.jsonl")
    existing_sentence_eval = _load_eval_pool(sources, "sentence_eval_pairs.jsonl")

    fresh_samples = _dedupe_rows(_read_jsonl(OUTPUT_DIR / "train_nllb_all.jsonl"), mode="sample")
    fresh_term_eval = _dedupe_rows(_read_jsonl(OUTPUT_DIR / "term_eval_pairs.jsonl"), mode="eval")
    fresh_sentence_eval = _dedupe_rows(_read_jsonl(OUTPUT_DIR / "sentence_eval_pairs.jsonl"), mode="eval")

    merged_samples = _dedupe_rows(existing_samples + fresh_samples, mode="sample")
    merged_term_eval = _dedupe_rows(existing_term_eval + fresh_term_eval, mode="eval")
    merged_sentence_eval = _dedupe_rows(existing_sentence_eval + fresh_sentence_eval, mode="eval")

    train_data, val_data, test_data = _split_dataset(merged_samples)

    _write_jsonl(OUTPUT_DIR / "train_nllb_all.jsonl", merged_samples)
    _write_jsonl(OUTPUT_DIR / "train_nllb_train.jsonl", train_data)
    _write_jsonl(OUTPUT_DIR / "train_nllb_val.jsonl", val_data)
    _write_jsonl(OUTPUT_DIR / "train_nllb_test.jsonl", test_data)
    _write_jsonl(OUTPUT_DIR / "term_eval_pairs.jsonl", merged_term_eval)
    _write_jsonl(OUTPUT_DIR / "sentence_eval_pairs.jsonl", merged_sentence_eval)

    stats = _compute_stats(
        samples_all=merged_samples,
        train_data=train_data,
        val_data=val_data,
        test_data=test_data,
        term_eval=merged_term_eval,
        sentence_eval=merged_sentence_eval,
    )
    stats["merge_mode"] = "append_dedup"
    stats["existing_sample_pool"] = len(existing_samples)
    stats["fresh_sample_pool"] = len(fresh_samples)
    stats["merged_sample_pool"] = len(merged_samples)
    stats["seed"] = SEED
    stats["train_ratio"] = TRAIN_RATIO
    stats["val_ratio"] = VAL_RATIO

    stats_path = OUTPUT_DIR / "data_stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def _load_entities_from_db() -> Tuple[List[Dict[str, Any]], str]:
    try:
        import django
        from django.apps import apps

        if not apps.ready:
            apps_dir = ROOT / "backend" / "apps"
            if str(apps_dir) not in sys.path:
                sys.path.insert(0, str(apps_dir))
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
            django.setup()

        from backend.apps.kb.models import KBEntity
        from backend.apps.kb.services import entity_to_export_record

        records = [entity_to_export_record(entity) for entity in KBEntity.objects.all().order_by("id")]
        records = [record for record in records if isinstance(record, dict)]
        if not records:
            return [], "no entities in KBEntity table"
        return records, ""
    except Exception as exc:
        return [], str(exc)


def _resolve_entities_path() -> Tuple[Path, str]:
    records, db_warning = _load_entities_from_db()
    if records:
        KB_ENTITIES_DB_EXPORT.parent.mkdir(parents=True, exist_ok=True)
        KB_ENTITIES_DB_EXPORT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        return KB_ENTITIES_DB_EXPORT, ""

    candidates = [KB_ENTITIES_APP, KB_ENTITIES]
    existing = [path for path in candidates if path.exists()]
    if not existing:
        checked = ", ".join(str(path) for path in candidates)
        if db_warning:
            raise FileNotFoundError(f"entities.json not found ({checked}); db warning: {db_warning}")
        raise FileNotFoundError(f"entities.json not found ({checked})")

    # Prefer the latest exported entities file when DB is unavailable.
    latest = max(existing, key=lambda path: path.stat().st_mtime)
    return latest, db_warning


def main() -> Dict[str, Any]:
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"generator script not found: {SCRIPT_PATH}")

    entities_path, db_warning = _resolve_entities_path()

    old_argv = sys.argv[:]
    sys.argv = [
        str(SCRIPT_PATH),
        "--entities",
        str(entities_path),
        "--output_dir",
        str(OUTPUT_DIR),
        "--seed",
        str(SEED),
        "--train_ratio",
        str(TRAIN_RATIO),
        "--val_ratio",
        str(VAL_RATIO),
        "--max_pairs_per_category",
        "50",
    ]
    try:
        runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
    finally:
        sys.argv = old_argv

    stats = _merge_incremental_outputs()
    stats["output_dir"] = str(OUTPUT_DIR)
    stats["entities_path"] = str(entities_path)
    if db_warning:
        stats["db_warning"] = db_warning
    return stats


if __name__ == "__main__":
    print(main())
