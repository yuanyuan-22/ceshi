#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NLLB-200-distilled-600M 的小样本 LoRA 微调脚本。

依赖：
  pip install transformers datasets peft accelerate sentencepiece sacrebleu evaluate

用法示例：
python ./scripts/train_nllb_lora.py `
  --model_name_or_path "./huggingface/hub/models--facebook--nllb-200-distilled-600M/snapshots/f8d333a098d19b4fd9a8b18f94170487ad3f821d" `
  --train_file "backend/data/nllb/train_nllb_train.jsonl" `
  --val_file "backend/data/nllb/train_nllb_val.jsonl" `
  --output_dir "scripts/models/nllb-medical-lora" `
  --per_device_train_batch_size 4 `
  --gradient_accumulation_steps 4 `
  --num_train_epochs 8

python ./scripts/train_nllb_lora.py \
  --model_name_or_path "./huggingface/hub/models--facebook--nllb-200-distilled-600M/snapshots/f8d333a098d19b4fd9a8b18f94170487ad3f821d" \
  --train_file "backend/data/nllb/train_nllb_train.jsonl" \
  --val_file "backend/data/nllb/train_nllb_val.jsonl" \
  --output_dir "scripts/models/nllb-medical-lora" \
  --per_device_train_batch_size 4 \
  --gradient_accumulation_steps 4 \
  --num_train_epochs 8

视情况该参数，我的是3060
这个是租的Quadro RTX 8000
python ./scripts/train_nllb_lora.py \
  --model_name_or_path "./huggingface/hub/models--facebook--nllb-200-distilled-600M/snapshots/f8d333a098d19b4fd9a8b18f94170487ad3f821d" \
  --train_file "backend/data/nllb/train_nllb_train.jsonl" \
  --val_file "backend/data/nllb/train_nllb_val.jsonl" \
  --output_dir "scripts/models/nllb-medical-lora-optimized" \
  --per_device_train_batch_size 32 \
  --per_device_eval_batch_size 32 \
  --gradient_accumulation_steps 1 \
  --eval_steps 500 \
  --save_steps 1000 \
  --logging_steps 25 \
  --num_train_epochs 20 \
  --learning_rate 3e-4 \
  --fp16
"""

from __future__ import annotations

import argparse
import csv
import inspect
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import torch
import transformers
from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    TrainerCallback,
)

os.environ.setdefault("WANDB_DISABLED", "true")

try:
    import evaluate
except Exception:
    evaluate = None

try:
    import sacrebleu
except Exception:
    sacrebleu = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_name_or_path", type=str, required=True)
    parser.add_argument("--train_file", type=str, required=True)
    parser.add_argument("--val_file", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--max_source_length", type=int, default=256)
    parser.add_argument("--max_target_length", type=int, default=256)
    parser.add_argument("--per_device_train_batch_size", type=int, default=4)
    parser.add_argument("--per_device_eval_batch_size", type=int, default=4)
    parser.add_argument("--gradient_accumulation_steps", type=int, default=4)
    parser.add_argument("--learning_rate", type=float, default=2e-4)
    parser.add_argument("--num_train_epochs", type=int, default=8)
    parser.add_argument("--eval_steps", type=int, default=50)
    parser.add_argument("--save_steps", type=int, default=50)
    parser.add_argument("--logging_steps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--lora_dropout", type=float, default=0.1)
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--bf16", action="store_true")
    return parser.parse_args()


def build_model_and_tokenizer(args: argparse.Namespace):
    model_name_or_path = args.model_name_or_path
    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, local_files_only=True)

    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForSeq2SeqLM.from_pretrained(
        model_name_or_path,
        dtype=dtype,
        local_files_only=True,
    )

    peft_config = LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        inference_mode=False,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "out_proj"],
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()
    return model, tokenizer


def preprocess_builder(tokenizer, max_source_length: int, max_target_length: int):
    def preprocess(example: Dict[str, Any]) -> Dict[str, Any]:
        src_lang = example["src_lang"]
        tgt_lang = example["tgt_lang"]

        if not src_lang:
            raise ValueError(f"src_lang is empty: {example}")
        if not tgt_lang:
            raise ValueError(f"tgt_lang is empty: {example}")

        # 先编码源文本
        tokenizer.src_lang = src_lang
        model_inputs = tokenizer(
            example["src_text"],
            truncation=True,
            max_length=max_source_length,
        )

        # 再编码目标文本
        tokenizer.src_lang = tgt_lang
        labels = tokenizer(
            example["tgt_text"],
            truncation=True,
            max_length=max_target_length,
        )

        model_inputs["labels"] = labels["input_ids"]
        model_inputs["forced_bos_token_id"] = tokenizer.convert_tokens_to_ids(tgt_lang)
        return model_inputs

    return preprocess

def compute_metrics_builder(tokenizer):
    metric_backend = None
    metric = None

    if sacrebleu is not None:
        metric_backend = "sacrebleu"

    if metric_backend is None and evaluate is not None:
        try:
            metric = evaluate.load("sacrebleu")
            metric_backend = "evaluate"
        except Exception as exc:
            print(f"[warning] evaluate.load('sacrebleu') failed: {exc}")

    if metric_backend is None:
        print("[warning] BLEU disabled: install `evaluate` or `sacrebleu` to enable eval_bleu")
        return None

    print(f"[metrics] BLEU backend={metric_backend}")

    def compute_metrics(eval_preds):
        preds, labels = eval_preds
        if isinstance(preds, tuple):
            preds = preds[0]

        decoded_preds = tokenizer.batch_decode(preds, skip_special_tokens=True)
        labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
        decoded_labels = tokenizer.batch_decode(labels, skip_special_tokens=True)

        decoded_preds = [x.strip() for x in decoded_preds]
        decoded_labels = [x.strip() for x in decoded_labels]

        if metric_backend == "evaluate":
            bleu = metric.compute(
                predictions=decoded_preds,
                references=[[x] for x in decoded_labels],
            )
            score = bleu["score"]
        else:
            score = sacrebleu.corpus_bleu(decoded_preds, [decoded_labels]).score

        return {"bleu": score}

    return compute_metrics


class MetricsLoggerCallback(TrainerCallback):
    """Print and persist per-log metrics for later curve plotting."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.jsonl_path = self.output_dir / "training_log.jsonl"
        if self.jsonl_path.exists():
            self.jsonl_path.unlink()

    def on_log(self, args, state, control, logs=None, **kwargs):
        if not logs:
            return

        payload: Dict[str, Any] = {
            "step": int(state.global_step),
            "epoch": round(float(state.epoch), 4) if state.epoch is not None else None,
        }
        payload.update(logs)

        printable_keys = [
            "step",
            "epoch",
            "loss",
            "learning_rate",
            "grad_norm",
            "eval_loss",
            "eval_bleu",
        ]
        printable = []
        for key in printable_keys:
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, float):
                printable.append(f"{key}={value:.6f}")
            else:
                printable.append(f"{key}={value}")
        if printable:
            print("[metrics] " + ", ".join(printable))

        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def save_log_history_files(log_history: List[Dict[str, Any]], output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    history_json = output_dir / "trainer_log_history.json"
    history_csv = output_dir / "trainer_log_history.csv"

    history_json.write_text(
        json.dumps(log_history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if not log_history:
        return

    preferred = [
        "step",
        "epoch",
        "loss",
        "learning_rate",
        "grad_norm",
        "eval_loss",
        "eval_bleu",
        "train_loss",
        "train_runtime",
        "train_samples_per_second",
        "train_steps_per_second",
    ]
    extra_keys = sorted({key for row in log_history for key in row.keys()} - set(preferred))
    fieldnames = [key for key in preferred if any(key in row for row in log_history)] + extra_keys

    with history_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in log_history:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


class NLLBSeq2SeqTrainer(Seq2SeqTrainer):
    def prediction_step(self, model, inputs, prediction_loss_only, ignore_keys=None, **gen_kwargs):
        if not prediction_loss_only:
            forced_bos_token_id = inputs.get("forced_bos_token_id")
            if forced_bos_token_id is not None:
                # 批内混合语言时，generate 只支持单个 forced_bos_token_id。
                # 所以这里退化为按 batch 第一个样本的目标语言生成。
                # 第一版建议先以 zh<->en 为主；若后续真正多语混训，可改成按语言分桶采样。
                if isinstance(forced_bos_token_id, torch.Tensor):
                    gen_kwargs["forced_bos_token_id"] = int(forced_bos_token_id[0].item())
                else:
                    gen_kwargs["forced_bos_token_id"] = int(forced_bos_token_id)
        return super().prediction_step(model, inputs, prediction_loss_only, ignore_keys=ignore_keys, **gen_kwargs)


def build_training_args(
    args: argparse.Namespace,
    metric_for_best_model: str,
    greater_is_better: bool,
) -> Seq2SeqTrainingArguments:
    save_steps = args.save_steps
    if save_steps % args.eval_steps != 0:
        adjusted_save_steps = ((save_steps + args.eval_steps - 1) // args.eval_steps) * args.eval_steps
        print(
            "[warning] save_steps must be a round multiple of eval_steps when "
            f"load_best_model_at_end=True; adjusting save_steps from {save_steps} to {adjusted_save_steps}"
        )
        save_steps = adjusted_save_steps

    signature = inspect.signature(Seq2SeqTrainingArguments.__init__)
    parameters = signature.parameters

    kwargs: Dict[str, Any] = {
        "output_dir": args.output_dir,
        "learning_rate": args.learning_rate,
        "per_device_train_batch_size": args.per_device_train_batch_size,
        "per_device_eval_batch_size": args.per_device_eval_batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "num_train_epochs": args.num_train_epochs,
        "logging_steps": args.logging_steps,
        "eval_steps": args.eval_steps,
        "save_steps": save_steps,
        "predict_with_generate": True,
        "fp16": args.fp16,
        "bf16": args.bf16,
        "report_to": "none",
        "load_best_model_at_end": True,
        "metric_for_best_model": metric_for_best_model,
        "greater_is_better": greater_is_better,
        "save_total_limit": 2,
        "seed": args.seed,
    }

    if "eval_strategy" in parameters:
        kwargs["eval_strategy"] = "steps"
    elif "evaluation_strategy" in parameters:
        kwargs["evaluation_strategy"] = "steps"
    else:
        raise TypeError("Seq2SeqTrainingArguments is missing eval/evaluation strategy parameter")

    if "save_strategy" in parameters:
        kwargs["save_strategy"] = "steps"

    return Seq2SeqTrainingArguments(**kwargs)


def build_trainer(
    args: argparse.Namespace,
    model,
    tokenizer,
    tokenized_datasets,
    data_collator,
    compute_metrics,
    training_args: Seq2SeqTrainingArguments,
) -> NLLBSeq2SeqTrainer:
    signature = inspect.signature(Seq2SeqTrainer.__init__)
    parameters = signature.parameters

    trainer_kwargs: Dict[str, Any] = {
        "model": model,
        "args": training_args,
        "train_dataset": tokenized_datasets["train"],
        "eval_dataset": tokenized_datasets["validation"],
        "data_collator": data_collator,
        "compute_metrics": compute_metrics,
        "callbacks": [MetricsLoggerCallback(args.output_dir)],
    }

    if "processing_class" in parameters:
        trainer_kwargs["processing_class"] = tokenizer
    elif "tokenizer" in parameters:
        trainer_kwargs["tokenizer"] = tokenizer

    print(
        "[compat] transformers="
        f"{transformers.__version__}, "
        f"trainer_tokenizer_arg={'processing_class' if 'processing_class' in parameters else 'tokenizer' if 'tokenizer' in parameters else 'none'}"
    )

    return NLLBSeq2SeqTrainer(**trainer_kwargs)



def main() -> None:
    args = parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    print("[stage] building model and tokenizer")
    model, tokenizer = build_model_and_tokenizer(args)

    print(f"[stage] loading dataset: train={args.train_file}, validation={args.val_file}")
    raw_datasets = load_dataset(
        "json",
        data_files={
            "train": args.train_file,
            "validation": args.val_file,
        },
    )
    print(
        "[stage] dataset loaded: "
        f"train={len(raw_datasets['train'])}, validation={len(raw_datasets['validation'])}"
    )

    preprocess = preprocess_builder(
        tokenizer=tokenizer,
        max_source_length=args.max_source_length,
        max_target_length=args.max_target_length,
    )

    print("[stage] tokenizing dataset")
    tokenized_datasets = raw_datasets.map(
        preprocess,
        remove_columns=raw_datasets["train"].column_names,
        desc="Tokenizing",
    )
    print(
        "[stage] tokenization complete: "
        f"train={len(tokenized_datasets['train'])}, validation={len(tokenized_datasets['validation'])}"
    )

    data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model, padding=True)
    print("[stage] building metrics")
    compute_metrics = compute_metrics_builder(tokenizer)
    metric_for_best_model = "bleu" if compute_metrics is not None else "eval_loss"
    greater_is_better = True if compute_metrics is not None else False

    training_args = build_training_args(
        args=args,
        metric_for_best_model=metric_for_best_model,
        greater_is_better=greater_is_better,
    )

    print("[stage] building trainer")
    trainer = build_trainer(
        args=args,
        model=model,
        tokenizer=tokenizer,
        tokenized_datasets=tokenized_datasets,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        training_args=training_args,
    )

    print("[stage] starting training")
    trainer.train()
    metrics = trainer.evaluate()
    print("eval_metrics=", json.dumps(metrics, ensure_ascii=False, indent=2))

    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    with open(Path(args.output_dir) / "final_eval_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    save_log_history_files(trainer.state.log_history, args.output_dir)
    print(f"Model saved to: {args.output_dir}")


if __name__ == "__main__":
    main()
