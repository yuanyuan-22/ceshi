#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download the `bigbio/paramed` source archive and save the original zh/en splits locally.

Output layout:
  backend/data/paramed/raw/
    train.jsonl
    val.jsonl
    test.jsonl
    manifest.json

Example:
  python scripts/download_paramed.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import tarfile

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "backend" / "data" / "paramed" / "raw"
DATASET_NAME = "bigbio/paramed"
ARCHIVE_URL = "https://github.com/boxiangliu/ParaMed/blob/master/data/nejm-open-access.tar.gz?raw=true"
ARCHIVE_NAME = "nejm-open-access.tar.gz"
EXTRACTED_DATA_DIR = Path("processed_data") / "open_access" / "open_access"
SPLIT_MAP = {
    "train": ("nejm.train.zh", "nejm.train.en", "train.jsonl"),
    "validation": ("nejm.dev.zh", "nejm.dev.en", "val.jsonl"),
    "test": ("nejm.test.zh", "nejm.test.en", "test.jsonl"),
}


def normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def iter_parallel_rows(zh_path: Path, en_path: Path):
    with zh_path.open("r", encoding="utf-8") as zh_f, en_path.open("r", encoding="utf-8") as en_f:
        for idx, (zh_line, en_line) in enumerate(zip(zh_f, en_f)):
            yield idx, normalize_text(zh_line), normalize_text(en_line)


def export_split(split_name: str, zh_path: Path, en_path: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for idx, zh_text, en_text in iter_parallel_rows(zh_path, en_path):
            if not zh_text or not en_text:
                continue

            payload = {
                "id": str(idx),
                "document_id": str(idx),
                "split": split_name,
                "zh_text": zh_text,
                "en_text": en_text,
                "source_dataset": DATASET_NAME,
                "license": "cc-by-4.0",
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            count += 1
    return count


def download_archive(archive_path: Path) -> None:
    with requests.get(ARCHIVE_URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with archive_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def extract_archive(archive_path: Path, extract_dir: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=extract_dir)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = OUTPUT_DIR / ARCHIVE_NAME
    extracted_root = OUTPUT_DIR / "extracted"
    if not archive_path.exists():
        print(f"[download_paramed] downloading archive: {ARCHIVE_URL}")
        download_archive(archive_path)
    else:
        print(f"[download_paramed] reuse archive: {archive_path}")

    if not (extracted_root / EXTRACTED_DATA_DIR).exists():
        print(f"[download_paramed] extracting archive to: {extracted_root}")
        extract_archive(archive_path, extracted_root)
    else:
        print(f"[download_paramed] reuse extracted files: {extracted_root / EXTRACTED_DATA_DIR}")

    data_dir = extracted_root / EXTRACTED_DATA_DIR

    split_counts: Dict[str, int] = {}
    for split_name, (zh_filename, en_filename, output_filename) in SPLIT_MAP.items():
        count = export_split(
            split_name,
            data_dir / zh_filename,
            data_dir / en_filename,
            OUTPUT_DIR / output_filename,
        )
        split_counts[split_name] = count
        print(f"[download_paramed] exported {split_name}: {count}")

    manifest = {
        "dataset": DATASET_NAME,
        "archive_url": ARCHIVE_URL,
        "archive_path": str(archive_path),
        "extracted_data_dir": str(data_dir),
        "output_dir": str(OUTPUT_DIR),
        "splits": split_counts,
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[download_paramed] manifest written: {OUTPUT_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()
