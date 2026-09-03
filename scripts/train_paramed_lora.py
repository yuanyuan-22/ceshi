#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thin wrapper around `scripts/train_nllb_lora.py` for ParaMed multilingual data.

Example:
  python scripts/train_paramed_lora.py --epochs 3
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "huggingface" / "hub" / "models--facebook--nllb-200-distilled-600M" / "snapshots" / "f8d333a098d19b4fd9a8b18f94170487ad3f821d"
TRAIN_SCRIPT = ROOT / "scripts" / "train_nllb_lora.py"
DATA_DIR = ROOT / "backend" / "data" / "paramed" / "nllb"
OUTPUT_DIR = ROOT / "scripts" / "models" / "nllb-paramed-lora"
HF_CACHE_DIR = ROOT / "huggingface"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python_executable", type=str, default=sys.executable)
    parser.add_argument("--output_dir", type=str, default=str(OUTPUT_DIR))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--learning_rate", type=float, default=2e-4)
    parser.add_argument("--max_source_length", type=int, default=160)
    parser.add_argument("--max_target_length", type=int, default=160)
    parser.add_argument("--per_device_train_batch_size", type=int, default=4)
    parser.add_argument("--per_device_eval_batch_size", type=int, default=4)
    parser.add_argument("--gradient_accumulation_steps", type=int, default=4)
    parser.add_argument("--eval_steps", type=int, default=500)
    parser.add_argument("--save_steps", type=int, default=1000)
    parser.add_argument("--logging_steps", type=int, default=25)
    parser.add_argument("--fp16", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    train_file = DATA_DIR / "train_nllb_train.jsonl"
    val_file = DATA_DIR / "train_nllb_val.jsonl"
    if not train_file.exists() or not val_file.exists():
        raise FileNotFoundError("paramed nllb training files not found; run build_paramed_multilang.py first")

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

    print("[train_paramed_lora] running:")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)


if __name__ == "__main__":
    main()
