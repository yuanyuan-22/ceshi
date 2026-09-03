#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Detokenize tokenized Chinese medical text.

This script is intended for ParaMed/NLLB preprocessing. It can:
1. Clean plain-text Chinese files such as `*.zh`
2. Clean selected string fields in `*.jsonl`
3. Process a directory recursively and mirror the output tree

Examples:
  python scripts/detokenize_paramed_chinese.py ^
    --input backend/data/paramed/raw/extracted/processed_data/open_access/open_access/nejm.train.zh ^
    --output backend/data/paramed/raw/extracted/processed_data/open_access/open_access/nejm.train.detok.zh

  python scripts/detokenize_paramed_chinese.py ^
    --input backend/data/paramed/raw/train.jsonl ^
    --fields zh_text ^
    --output backend/data/paramed/raw/train.detok.jsonl

  python scripts/detokenize_paramed_chinese.py ^
    --input backend/data/paramed/raw/extracted/processed_data/open_access/open_access ^
    --recursive
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
CJK_RANGE = r"\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff"

DEFAULT_JSONL_FIELDS = ["zh_text"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="Input file or directory.")
    parser.add_argument("--output", type=Path, default=None, help="Output file or directory.")
    parser.add_argument("--fields", type=str, default="zh_text", help="Comma-separated jsonl fields to clean.")
    parser.add_argument("--recursive", action="store_true", help="Process directories recursively.")
    parser.add_argument("--inplace", action="store_true", help="Overwrite the input file(s).")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files.")
    parser.add_argument("--report_json", type=Path, default=None, help="Optional path for a JSON summary.")
    return parser.parse_args()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_cjk_text(text: str) -> bool:
    return bool(re.search(rf"[{CJK_RANGE}]", text or ""))


def detokenize_zh_text(text: str) -> str:
    text = normalize_whitespace(text)
    if not text:
        return text

    text = text.replace("@-@", "-")
    text = text.replace("@ - @", "-")

    # Remove spaces between adjacent Chinese/Japanese characters and around CJK/ASCII boundaries.
    text = re.sub(rf"(?<=[{CJK_RANGE}])\s+(?=[{CJK_RANGE}])", "", text)
    text = re.sub(rf"(?<=[{CJK_RANGE}])\s+(?=[A-Za-z0-9])", "", text)
    text = re.sub(rf"(?<=[A-Za-z0-9])\s+(?=[{CJK_RANGE}])", "", text)
    text = re.sub(r"(?<=\d)\s+(?=%)", "", text)
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)

    # Remove spaces before punctuation that should attach to the previous token.
    text = re.sub(r"\s*([,.;:!?])\s*", r"\1", text)
    text = re.sub(r"\s*([()\[\]{}])\s*", r"\1", text)

    # Normalize common Chinese punctuation.
    text = re.sub(r"(?<!\d),(?!\d)", "，", text)
    text = re.sub(r"(?<!\d);", "；", text)
    text = re.sub(r"(?<!\d):", "：", text)
    text = re.sub(r"(?<!\d)\?(?!\d)", "？", text)
    text = re.sub(r"(?<!\d)!(?!\d)", "！", text)
    text = text.replace("(", "（").replace(")", "）")

    # Convert a sentence-final period, but keep internal periods such as abbreviations.
    text = re.sub(rf"\.(?=(?:[）)\]】》」』”’\"']|\s|$))", "。", text)

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detokenize_text(text: str) -> str:
    if not text:
        return text
    if is_cjk_text(text):
        return detokenize_zh_text(text)
    return normalize_whitespace(text)


def resolve_output_path(input_path: Path, output: Path | None, inplace: bool) -> Path:
    if inplace:
        return input_path

    if output is not None:
        if input_path.is_file():
            return output
        return output

    if input_path.is_file():
        if input_path.suffix == ".jsonl":
            return input_path.with_name(f"{input_path.stem}.detok{input_path.suffix}")
        return input_path.with_name(f"{input_path.stem}.detok{input_path.suffix}")

    return input_path.with_name(f"{input_path.name}.detok")


def iter_input_files(input_path: Path, recursive: bool) -> Iterator[Path]:
    if input_path.is_file():
        yield input_path
        return

    patterns = ("*.zh", "*.jsonl", "*.txt")
    if recursive:
        for pattern in patterns:
            yield from input_path.rglob(pattern)
    else:
        for pattern in patterns:
            yield from input_path.glob(pattern)


def process_text_file(input_path: Path, output_path: Path) -> Dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    changed = 0
    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8", newline="\n") as dst:
        for line in src:
            total += 1
            raw = line.rstrip("\n")
            cleaned = detokenize_text(raw)
            if cleaned != raw:
                changed += 1
            dst.write(cleaned + "\n")
    return {"type": "text", "input": str(input_path), "output": str(output_path), "lines": total, "changed_lines": changed}


def process_jsonl_file(input_path: Path, output_path: Path, fields: List[str]) -> Dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    changed_rows = 0
    changed_fields = 0
    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8", newline="\n") as dst:
        for line_no, line in enumerate(src, start=1):
            raw = line.strip()
            if not raw:
                continue
            total += 1
            row = json.loads(raw)
            row_changed = False
            for field in fields:
                value = row.get(field)
                if isinstance(value, str):
                    cleaned = detokenize_text(value)
                    if cleaned != value:
                        row_changed = True
                        changed_fields += 1
                    row[field] = cleaned
            if row_changed:
                changed_rows += 1
            dst.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "type": "jsonl",
        "input": str(input_path),
        "output": str(output_path),
        "rows": total,
        "changed_rows": changed_rows,
        "changed_fields": changed_fields,
        "fields": fields,
    }


def build_file_output_path(input_root: Path, input_file: Path, output_root: Path | None, inplace: bool) -> Path:
    if inplace:
        return input_file

    if output_root is None:
        return resolve_output_path(input_file, None, False)

    # When processing a directory, treat the output as a directory root even if
    # its name contains a suffix-like tail such as ".detok".
    if input_root.is_file() and output_root.suffix:
        return output_root

    relative_path = input_file.relative_to(input_root)
    relative_name = relative_path.name
    if input_file.suffix == ".jsonl":
        relative_name = f"{input_file.stem}.detok{input_file.suffix}"
    elif input_file.suffix:
        relative_name = f"{input_file.stem}.detok{input_file.suffix}"
    return output_root / relative_path.parent / relative_name


def main() -> None:
    args = parse_args()
    input_path = args.input
    if not input_path.exists():
        raise FileNotFoundError(f"input not found: {input_path}")

    fields = [field.strip() for field in args.fields.split(",") if field.strip()]
    if not fields:
        fields = DEFAULT_JSONL_FIELDS[:]

    report: List[Dict[str, Any]] = []

    if input_path.is_file():
        output_path = resolve_output_path(input_path, args.output, args.inplace)
        if output_path.exists() and output_path != input_path and not args.force:
            raise FileExistsError(f"output exists: {output_path} (use --force to overwrite)")
        if input_path.suffix == ".jsonl":
            summary = process_jsonl_file(input_path, output_path, fields)
        else:
            summary = process_text_file(input_path, output_path)
        report.append(summary)
    else:
        output_root = args.output
        if output_root is None:
            output_root = input_path.with_name(f"{input_path.name}.detok")
        if output_root.exists():
            if output_root.is_file():
                raise FileExistsError(
                    f"output path is an existing file, not a directory: {output_root}. "
                    f"Choose a different --output or delete that file first."
                )
            if not args.force and not args.inplace:
                # Allow re-running into a populated tree only when --force is set.
                raise FileExistsError(f"output directory exists: {output_root} (use --force to overwrite)")

        for file_path in iter_input_files(input_path, args.recursive):
            if file_path.suffix not in {".zh", ".txt", ".jsonl"}:
                continue
            out_path = build_file_output_path(input_path, file_path, output_root, args.inplace)
            if out_path.exists() and out_path != file_path and not args.force:
                raise FileExistsError(f"output exists: {out_path} (use --force to overwrite)")
            if file_path.suffix == ".jsonl":
                summary = process_jsonl_file(file_path, out_path, fields)
            else:
                summary = process_text_file(file_path, out_path)
            report.append(summary)

    payload = {"files": report}
    if args.report_json is not None:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
