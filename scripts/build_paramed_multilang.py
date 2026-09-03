#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Expand the ParaMed zh/en corpus into the project's multilingual NLLB jsonl format.

Pipeline:
1. Read zh/en raw jsonl exported by `download_paramed.py`
2. Use `backend/data/kb_raw/apidemo/TranslateDemo_auto.py` translation helpers
   to translate zh into ja/fr/de
3. Build multilingual sentence pairs in the same schema used by training

Output layout:
  backend/data/paramed/nllb/
    train_nllb_train.jsonl
    train_nllb_val.jsonl
    train_nllb_test.jsonl
    train_nllb_all.jsonl
    data_stats.json

Example:
  python scripts/build_paramed_multilang.py --limit_per_split 200
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "backend" / "data" / "paramed" / "raw"
OUTPUT_DIR = ROOT / "backend" / "data" / "paramed" / "nllb"
TRANSLATE_DEMO_PATH = ROOT / "backend" / "data" / "kb_raw" / "apidemo" / "TranslateDemo_auto.py"
CACHE_DIRNAME = "translation_cache"
PROGRESS_FILENAME = "progress.json"

LANG_TO_NLLB = {
    "zh": "zho_Hans",
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "ja": "jpn_Jpan",
}
TARGET_LANGS = ["ja", "fr", "de"]
RAW_SPLITS = {
    "train": RAW_DIR / "train.jsonl",
    "validation": RAW_DIR / "val.jsonl",
    "test": RAW_DIR / "test.jsonl",
}
OUTPUT_SPLITS = {
    "train": OUTPUT_DIR / "train_nllb_train.jsonl",
    "validation": OUTPUT_DIR / "train_nllb_val.jsonl",
    "test": OUTPUT_DIR / "train_nllb_test.jsonl",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw_dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output_dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--limit_per_split", type=int, default=0, help="0 means no limit")
    parser.add_argument("--sleep_sec", type=float, default=0.8)
    parser.add_argument("--retry_attempts", type=int, default=6)
    parser.add_argument("--retry_wait_sec", type=float, default=8.0)
    parser.add_argument("--retry_backoff", type=float, default=1.8)
    parser.add_argument("--flush_every", type=int, default=20)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def resolve_raw_split_paths(raw_dir: Path) -> Dict[str, Path]:
    split_candidates = {
        "train": ["train.detok.jsonl", "train.jsonl"],
        "validation": ["val.detok.jsonl", "validation.detok.jsonl", "val.jsonl", "validation.jsonl"],
        "test": ["test.detok.jsonl", "test.jsonl"],
    }

    resolved: Dict[str, Path] = {}
    for split_name, candidates in split_candidates.items():
        for filename in candidates:
            path = raw_dir / filename
            if path.exists():
                resolved[split_name] = path
                break
        else:
            resolved[split_name] = raw_dir / candidates[0]
    return resolved


def load_translate_demo():
    spec = importlib.util.spec_from_file_location("translate_demo_auto", TRANSLATE_DEMO_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load translate demo script: {TRANSLATE_DEMO_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_error_message(exc: Exception) -> str:
    return normalize_text(str(exc))


def is_rate_limit_error(exc: Exception) -> bool:
    message = normalize_error_message(exc)
    return "errorCode=411" in message or "errorCode\": \"411\"" in message


def read_jsonl(path: Path, limit: int = 0) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    return rows


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(row.get("src_lang", "")),
        str(row.get("tgt_lang", "")),
        normalize_text(row.get("src_text", "")),
        normalize_text(row.get("tgt_text", "")),
    )


def translation_cache_path(output_dir: Path, split: str) -> Path:
    return output_dir / CACHE_DIRNAME / f"{split}.json"


def load_translation_cache(output_dir: Path, split: str) -> Dict[str, Dict[str, str]]:
    data = load_json(translation_cache_path(output_dir, split), {})
    return data if isinstance(data, dict) else {}


def save_translation_cache(output_dir: Path, split: str, cache: Dict[str, Dict[str, str]]) -> None:
    write_json(translation_cache_path(output_dir, split), cache)


def progress_path(output_dir: Path) -> Path:
    return output_dir / PROGRESS_FILENAME


def load_progress(output_dir: Path) -> Dict[str, int]:
    data = load_json(progress_path(output_dir), {})
    return data if isinstance(data, dict) else {}


def save_progress(output_dir: Path, progress: Dict[str, int]) -> None:
    write_json(progress_path(output_dir), progress)


def build_row(
    *,
    split: str,
    document_id: str,
    src_lang: str,
    tgt_lang: str,
    src_text: str,
    tgt_text: str,
) -> Dict[str, Any]:
    return {
        "src_text": normalize_text(src_text),
        "tgt_text": normalize_text(tgt_text),
        "src_lang": LANG_TO_NLLB[src_lang],
        "tgt_lang": LANG_TO_NLLB[tgt_lang],
        "sample_type": "paramed_parallel_sentence",
        "entity_id": f"paramed_{document_id}",
        "canonical_key": f"paramed_doc_{document_id}",
        "category": "medical_parallel_corpus",
        "text_field": "sentence",
        "meta": {
            "source_dataset": "bigbio/paramed",
            "split": split,
            "src_lang": src_lang,
            "tgt_lang": tgt_lang,
        },
    }


def record_cache_key(record: Dict[str, Any]) -> str:
    document_id = str(record.get("document_id", record.get("id", ""))).strip() or "0"
    zh_text = normalize_text(record.get("zh_text", ""))
    return f"{document_id}|||{zh_text}"


def translate_with_retry(
    translator_module,
    zh_text: str,
    to_lang: str,
    retry_attempts: int,
    retry_wait_sec: float,
    retry_backoff: float,
    sleep_sec: float,
) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, retry_attempts + 1):
        try:
            translated = translator_module.translate_text(zh_text, "zh", to_lang)
            return normalize_text(translated)
        except Exception as exc:
            last_exc = exc
            if not is_rate_limit_error(exc) or attempt >= retry_attempts:
                raise

            wait_sec = retry_wait_sec * (retry_backoff ** (attempt - 1))
            print(
                f"[build_paramed_multilang] rate-limited for {to_lang}, "
                f"retry {attempt}/{retry_attempts} after {wait_sec:.1f}s"
            )
            time.sleep(wait_sec)
        finally:
            if sleep_sec > 0:
                time.sleep(sleep_sec)

    if last_exc is not None:
        raise last_exc
    return ""


def translate_targets(
    translator_module,
    zh_text: str,
    cache_bucket: Dict[str, str],
    sleep_sec: float,
    retry_attempts: int,
    retry_wait_sec: float,
    retry_backoff: float,
    counters: Dict[str, Dict[str, int]],
) -> Dict[str, str]:
    translated: Dict[str, str] = {}
    for lang in TARGET_LANGS:
        if normalize_text(cache_bucket.get(lang, "")):
            translated[lang] = normalize_text(cache_bucket.get(lang, ""))
            counters.setdefault(lang, {}).setdefault("cache_hit", 0)
            counters[lang]["cache_hit"] += 1
            continue

        try:
            translated_text = translate_with_retry(
                translator_module=translator_module,
                zh_text=zh_text,
                to_lang=lang,
                retry_attempts=retry_attempts,
                retry_wait_sec=retry_wait_sec,
                retry_backoff=retry_backoff,
                sleep_sec=sleep_sec,
            )
            translated[lang] = translated_text
            cache_bucket[lang] = translated_text
            counters.setdefault(lang, {}).setdefault("success", 0)
            counters[lang]["success"] += 1
        except Exception as exc:
            print(f"[build_paramed_multilang] skip {lang} translation: {exc}")
            translated[lang] = ""
            counters.setdefault(lang, {}).setdefault("failed", 0)
            counters[lang]["failed"] += 1
    return translated


def build_rows_for_record(
    translator_module,
    record: Dict[str, Any],
    split: str,
    cache_bucket: Dict[str, str],
    sleep_sec: float,
    retry_attempts: int,
    retry_wait_sec: float,
    retry_backoff: float,
    counters: Dict[str, Dict[str, int]],
) -> List[Dict[str, Any]]:
    zh_text = normalize_text(record.get("zh_text", ""))
    en_text = normalize_text(record.get("en_text", ""))
    document_id = str(record.get("document_id", record.get("id", ""))).strip() or "0"
    if not zh_text or not en_text:
        return []

    texts_by_lang: Dict[str, str] = {
        "zh": zh_text,
        "en": en_text,
    }
    texts_by_lang.update(
        translate_targets(
            translator_module=translator_module,
            zh_text=zh_text,
            cache_bucket=cache_bucket,
            sleep_sec=sleep_sec,
            retry_attempts=retry_attempts,
            retry_wait_sec=retry_wait_sec,
            retry_backoff=retry_backoff,
            counters=counters,
        )
    )

    rows: List[Dict[str, Any]] = []
    seen = set()
    langs = [lang for lang in ("zh", "en", "ja", "fr", "de") if normalize_text(texts_by_lang.get(lang, ""))]
    for src_lang in langs:
        for tgt_lang in langs:
            if src_lang == tgt_lang:
                continue
            row = build_row(
                split=split,
                document_id=document_id,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
                src_text=texts_by_lang[src_lang],
                tgt_text=texts_by_lang[tgt_lang],
            )
            key = sample_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def main() -> None:
    args = parse_args()
    translator_module = load_translate_demo()
    raw_splits = resolve_raw_split_paths(args.raw_dir)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    split_rows: Dict[str, List[Dict[str, Any]]] = {
        "train": read_jsonl(OUTPUT_SPLITS["train"]) if args.resume else [],
        "validation": read_jsonl(OUTPUT_SPLITS["validation"]) if args.resume else [],
        "test": read_jsonl(OUTPUT_SPLITS["test"]) if args.resume else [],
    }
    progress = load_progress(args.output_dir) if args.resume else {}
    counters: Dict[str, Dict[str, int]] = {}

    for split_name, input_path in raw_splits.items():
        if not input_path.exists():
            candidate_text = ", ".join(path.name for path in [args.raw_dir / name for name in {
                "train": ["train.detok.jsonl", "train.jsonl"],
                "validation": ["val.detok.jsonl", "validation.detok.jsonl", "val.jsonl", "validation.jsonl"],
                "test": ["test.detok.jsonl", "test.jsonl"],
            }[split_name]])
            raise FileNotFoundError(
                f"raw split not found for {split_name} under {args.raw_dir}. "
                f"searched: {candidate_text}"
            )

        records = read_jsonl(input_path, limit=args.limit_per_split)
        print(f"[build_paramed_multilang] loaded {split_name}: {len(records)} records from {input_path.name}")
        cache = load_translation_cache(args.output_dir, split_name)
        start_index = progress.get(split_name, 0) if args.resume else 0
        if start_index:
            print(f"[build_paramed_multilang] resume {split_name} from record {start_index}")

        for index, record in enumerate(records, start=1):
            if index <= start_index:
                continue

            cache_key = record_cache_key(record)
            cache_bucket = cache.get(cache_key)
            if not isinstance(cache_bucket, dict):
                cache_bucket = {}
                cache[cache_key] = cache_bucket

            rows = build_rows_for_record(
                translator_module=translator_module,
                record=record,
                split=split_name,
                cache_bucket=cache_bucket,
                sleep_sec=args.sleep_sec,
                retry_attempts=args.retry_attempts,
                retry_wait_sec=args.retry_wait_sec,
                retry_backoff=args.retry_backoff,
                counters=counters,
            )
            split_rows[split_name].extend(rows)
            progress[split_name] = index

            if index % args.flush_every == 0:
                save_translation_cache(args.output_dir, split_name, cache)
                save_progress(args.output_dir, progress)

            if index % 20 == 0:
                print(f"[build_paramed_multilang] {split_name}: processed {index}/{len(records)}")

        save_translation_cache(args.output_dir, split_name, cache)
        save_progress(args.output_dir, progress)

    all_rows = split_rows["train"] + split_rows["validation"] + split_rows["test"]

    counts = {
        "train": write_jsonl(OUTPUT_SPLITS["train"], split_rows["train"]),
        "validation": write_jsonl(OUTPUT_SPLITS["validation"], split_rows["validation"]),
        "test": write_jsonl(OUTPUT_SPLITS["test"], split_rows["test"]),
        "all": write_jsonl(args.output_dir / "train_nllb_all.jsonl", all_rows),
    }

    lang_pairs: Dict[str, int] = {}
    for row in all_rows:
        key = f"{row['src_lang']}->{row['tgt_lang']}"
        lang_pairs[key] = lang_pairs.get(key, 0) + 1

    stats = {
        "source_dataset": "bigbio/paramed",
        "raw_dir": str(args.raw_dir),
        "raw_split_files": {key: str(value) for key, value in raw_splits.items()},
        "output_dir": str(args.output_dir),
        "limit_per_split": args.limit_per_split,
        "num_train_samples": counts["train"],
        "num_val_samples": counts["validation"],
        "num_test_samples": counts["test"],
        "num_all_samples": counts["all"],
        "language_pair_distribution": lang_pairs,
        "translation_counters": counters,
        "resume": args.resume,
        "retry_attempts": args.retry_attempts,
        "retry_wait_sec": args.retry_wait_sec,
        "retry_backoff": args.retry_backoff,
        "sleep_sec": args.sleep_sec,
    }
    (args.output_dir / "data_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[build_paramed_multilang] done: {args.output_dir}")


if __name__ == "__main__":
    main()
