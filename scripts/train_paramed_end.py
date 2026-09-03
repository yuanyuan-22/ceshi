#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Train NLLB LoRA on the detokenized ParaMed multilingual corpus.

This entrypoint keeps `train_paramed_lora.py` unchanged and does not call the
translation API again. It reuses the existing multilingual dataset under:
  backend/data/paramed/nllb/

Then it replaces every Chinese (`zho_Hans`) sentence in that dataset with the
detokenized Chinese text from:
  backend/data/paramed/raw/train.detok.jsonl
  backend/data/paramed/raw/val.detok.jsonl
  backend/data/paramed/raw/test.detok.jsonl

Examples:
  python scripts/train_paramed_end.py

  python scripts/train_paramed_end.py --epochs 10 --fp16

  python scripts/train_paramed_end.py --prepare_only --rebuild_data
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "huggingface" / "hub" / "models--facebook--nllb-200-distilled-600M" / "snapshots" / "f8d333a098d19b4fd9a8b18f94170487ad3f821d"
TRAIN_SCRIPT = ROOT / "scripts" / "train_nllb_lora.py"
RAW_DIR = ROOT / "backend" / "data" / "paramed" / "raw"
SOURCE_DATA_DIR = ROOT / "backend" / "data" / "paramed" / "nllb"
DATA_DIR = ROOT / "backend" / "data" / "paramed" / "nllb_detok_multilang"
OUTPUT_DIR = ROOT / "scripts" / "models" / "nllb-paramed-detok-multilang-e10"
HF_CACHE_DIR = ROOT / "huggingface"

RAW_SPLITS = {
    "train": "train.detok.jsonl",
    "validation": "val.detok.jsonl",
    "test": "test.detok.jsonl",
}
DATA_SPLITS = {
    "train": "train_nllb_train.jsonl",
    "validation": "train_nllb_val.jsonl",
    "test": "train_nllb_test.jsonl",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python_executable", type=str, default=sys.executable)
    parser.add_argument("--raw_dir", type=str, default=str(RAW_DIR))
    parser.add_argument("--source_data_dir", type=str, default=str(SOURCE_DATA_DIR))
    parser.add_argument("--data_dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--output_dir", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--learning_rate", type=float, default=2e-4)
    parser.add_argument("--max_source_length", type=int, default=160)
    parser.add_argument("--max_target_length", type=int, default=160)
    parser.add_argument("--per_device_train_batch_size", type=int, default=4)
    parser.add_argument("--per_device_eval_batch_size", type=int, default=4)
    parser.add_argument("--gradient_accumulation_steps", type=int, default=4)
    parser.add_argument("--eval_steps", type=int, default=500)
    parser.add_argument("--save_steps", type=int, default=1000)
    parser.add_argument("--logging_steps", type=int, default=25)
    parser.add_argument("--limit_per_split", type=int, default=0, help="0 means no limit")
    parser.add_argument("--prepare_only", action="store_true")
    parser.add_argument("--rebuild_data", action="store_true")
    parser.add_argument("--fp16", action="store_true")
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def read_jsonl(path: Path, limit: int = 0) -> List[Dict[str, Any]]:
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


def make_detok_key(split_name: str, entity_id: str) -> str:
    return f"{split_name}::{entity_id}"


def build_detok_index(raw_dir: Path, limit_per_split: int) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for split_name, filename in RAW_SPLITS.items():
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"detok raw split not found for {split_name}: {path}")

        for record in read_jsonl(path, limit=limit_per_split):
            zh_text = normalize_text(record.get("zh_text", ""))
            if not zh_text:
                continue
            document_id = str(record.get("document_id", record.get("id", ""))).strip() or "0"
            entity_id = f"paramed_{document_id}"
            index[make_detok_key(split_name, entity_id)] = zh_text
    if not index:
        raise RuntimeError(f"no detokenized zh_text records found under: {raw_dir}")
    return index


def rewrite_row_with_detok_zh(
    row: Dict[str, Any],
    detok_index: Dict[str, str],
    split_name: str,
) -> tuple[Dict[str, Any], int, int]:
    rewritten = dict(row)
    entity_id = str(rewritten.get("entity_id", "")).strip()
    detok_zh = detok_index.get(make_detok_key(split_name, entity_id))
    src_replaced = 0
    tgt_replaced = 0

    if detok_zh and rewritten.get("src_lang") == "zho_Hans":
        rewritten["src_text"] = detok_zh
        src_replaced = 1
    if detok_zh and rewritten.get("tgt_lang") == "zho_Hans":
        rewritten["tgt_text"] = detok_zh
        tgt_replaced = 1

    return rewritten, src_replaced, tgt_replaced


def prepare_dataset(
    source_data_dir: Path,
    raw_dir: Path,
    data_dir: Path,
    limit_per_split: int,
    rebuild_data: bool,
) -> Dict[str, Any]:
    output_paths = {split: data_dir / filename for split, filename in DATA_SPLITS.items()}

    if not rebuild_data and all(path.exists() for path in output_paths.values()):
        stats_path = data_dir / "data_stats.json"
        stats = {}
        if stats_path.exists():
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
        print(f"[train_paramed_end] reuse prepared dataset: {data_dir}")
        return stats

    source_paths = {split: source_data_dir / filename for split, filename in DATA_SPLITS.items()}
    for split, path in source_paths.items():
        if not path.exists():
            raise FileNotFoundError(f"source nllb split not found for {split}: {path}")

    detok_index = build_detok_index(raw_dir, limit_per_split=limit_per_split)
    data_dir.mkdir(parents=True, exist_ok=True)

    split_counts: Dict[str, int] = {}
    source_counts: Dict[str, int] = {}
    zh_src_replacements: Dict[str, int] = {}
    zh_tgt_replacements: Dict[str, int] = {}
    pair_counts: Dict[str, int] = {}
    all_rows: List[Dict[str, Any]] = []

    for split, input_path in source_paths.items():
        source_rows = read_jsonl(input_path, limit=limit_per_split)
        source_counts[split] = len(source_rows)

        output_rows: List[Dict[str, Any]] = []
        src_replaced_total = 0
        tgt_replaced_total = 0

        for row in source_rows:
            rewritten, src_replaced, tgt_replaced = rewrite_row_with_detok_zh(
                row=row,
                detok_index=detok_index,
                split_name=split,
            )
            output_rows.append(rewritten)
            src_replaced_total += src_replaced
            tgt_replaced_total += tgt_replaced

            pair_key = f"{rewritten['src_lang']}->{rewritten['tgt_lang']}"
            pair_counts[pair_key] = pair_counts.get(pair_key, 0) + 1

        split_counts[split] = write_jsonl(output_paths[split], output_rows)
        zh_src_replacements[split] = src_replaced_total
        zh_tgt_replacements[split] = tgt_replaced_total
        all_rows.extend(output_rows)

        print(
            f"[train_paramed_end] prepared {split}: "
            f"{len(source_rows)} source rows -> {split_counts[split]} rows, "
            f"zh_src_replaced={src_replaced_total}, zh_tgt_replaced={tgt_replaced_total}"
        )

    all_path = data_dir / "train_nllb_all.jsonl"
    all_count = write_jsonl(all_path, all_rows)

    stats = {
        "source_dataset": "bigbio/paramed",
        "raw_dir": str(raw_dir),
        "source_data_dir": str(source_data_dir),
        "data_dir": str(data_dir),
        "raw_split_files": {split: str(raw_dir / filename) for split, filename in RAW_SPLITS.items()},
        "source_split_files": {split: str(path) for split, path in source_paths.items()},
        "prepared_split_files": {split: str(path) for split, path in output_paths.items()},
        "prepared_all_file": str(all_path),
        "limit_per_split": limit_per_split,
        "detok_index_size": len(detok_index),
        "source_row_counts": source_counts,
        "prepared_row_counts": split_counts,
        "prepared_total_rows": all_count,
        "zh_src_replacements": zh_src_replacements,
        "zh_tgt_replacements": zh_tgt_replacements,
        "language_pair_distribution": pair_counts,
    }
    (data_dir / "data_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return stats


def run_training(args: argparse.Namespace, train_file: Path, val_file: Path) -> None:
    env = os.environ.copy()
    env.setdefault("HF_HOME", str(HF_CACHE_DIR))
    env.setdefault("HF_DATASETS_CACHE", str(HF_CACHE_DIR / "datasets"))
    env.setdefault("TRANSFORMERS_CACHE", str(HF_CACHE_DIR / "hub"))

    cmd = [
        args.python_executable,
        str(TRAIN_SCRIPT),
        "--model_name_or_path",
        str(MODEL_PATH),
        "--train_file",
        str(train_file),
        "--val_file",
        str(val_file),
        "--output_dir",
        str(args.output_dir),
        "--max_source_length",
        str(args.max_source_length),
        "--max_target_length",
        str(args.max_target_length),
        "--per_device_train_batch_size",
        str(args.per_device_train_batch_size),
        "--per_device_eval_batch_size",
        str(args.per_device_eval_batch_size),
        "--gradient_accumulation_steps",
        str(args.gradient_accumulation_steps),
        "--num_train_epochs",
        str(args.epochs),
        "--learning_rate",
        str(args.learning_rate),
        "--eval_steps",
        str(args.eval_steps),
        "--save_steps",
        str(args.save_steps),
        "--logging_steps",
        str(args.logging_steps),
    ]
    if args.fp16:
        cmd.append("--fp16")

    print("[train_paramed_end] running:")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)


def main() -> None:
    args = parse_args()

    raw_dir = Path(args.raw_dir)
    source_data_dir = Path(args.source_data_dir)
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    if not raw_dir.exists():
        raise FileNotFoundError(f"raw_dir not found: {raw_dir}")
    if not source_data_dir.exists():
        raise FileNotFoundError(f"source_data_dir not found: {source_data_dir}")
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"base model not found: {MODEL_PATH}")
    if not TRAIN_SCRIPT.exists():
        raise FileNotFoundError(f"train script not found: {TRAIN_SCRIPT}")

    stats = prepare_dataset(
        source_data_dir=source_data_dir,
        raw_dir=raw_dir,
        data_dir=data_dir,
        limit_per_split=args.limit_per_split,
        rebuild_data=args.rebuild_data,
    )
    train_file = data_dir / DATA_SPLITS["train"]
    val_file = data_dir / DATA_SPLITS["validation"]

    print(f"[train_paramed_end] source data dir: {source_data_dir}")
    print(f"[train_paramed_end] train file      : {train_file}")
    print(f"[train_paramed_end] val file        : {val_file}")
    if stats:
        print(f"[train_paramed_end] prepared rows  : {stats.get('prepared_row_counts', {})}")
        print(f"[train_paramed_end] zh src replace : {stats.get('zh_src_replacements', {})}")
        print(f"[train_paramed_end] zh tgt replace : {stats.get('zh_tgt_replacements', {})}")

    if args.prepare_only:
        print("[train_paramed_end] prepare_only enabled, skip training")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    run_training(args, train_file, val_file)


if __name__ == "__main__":
    main()
