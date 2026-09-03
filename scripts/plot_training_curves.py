#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plot thesis-friendly training curves from train_nllb_lora.py outputs.

Supported log sources under model_dir:
  - training_log.jsonl
  - trainer_log_history.json
  - trainer_log_history.csv
  - latest checkpoint-*/trainer_state.json

Examples:
  python scripts/plot_training_curves.py --model_dir scripts/models/nllb-paramed-lora-1000-e20-b24
  python scripts/plot_training_curves.py --model_dir scripts/models/nllb-paramed-lora-1000-e20-b24 --smooth_window 20
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams


def configure_matplotlib() -> None:
    rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    rcParams["axes.unicode_minus"] = False
    rcParams["figure.facecolor"] = "white"
    rcParams["axes.facecolor"] = "white"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", type=str, required=True)
    parser.add_argument("--log_file", type=str, default=None, help="Optional explicit path to a log file.")
    parser.add_argument("--smooth_window", type=int, default=10, help="Moving-average window for train loss.")
    parser.add_argument("--dpi", type=int, default=160)
    return parser.parse_args()


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def read_json(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("log_history"), list):
        return payload["log_history"]
    raise RuntimeError(f"unsupported json structure: {path}")


def read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cleaned: Dict[str, Any] = {}
            for key, value in row.items():
                if value is None or value == "":
                    continue
                try:
                    if "." in value or "e" in value.lower():
                        cleaned[key] = float(value)
                    else:
                        cleaned[key] = int(value)
                except Exception:
                    cleaned[key] = value
            rows.append(cleaned)
    return rows


def find_latest_checkpoint_trainer_state(model_dir: Path) -> Path | None:
    trainer_states = sorted(model_dir.glob("checkpoint-*/trainer_state.json"))
    if not trainer_states:
        return None

    def checkpoint_step(path: Path) -> int:
        name = path.parent.name
        try:
            return int(name.split("-")[-1])
        except Exception:
            return -1

    return max(trainer_states, key=checkpoint_step)


def load_rows(model_dir: Path, explicit_log_file: str | None) -> tuple[List[Dict[str, Any]], Path]:
    if explicit_log_file:
        path = Path(explicit_log_file)
        if not path.exists():
            raise FileNotFoundError(f"log file not found: {path}")
        if path.suffix == ".jsonl":
            return read_jsonl(path), path
        if path.suffix == ".json":
            return read_json(path), path
        if path.suffix == ".csv":
            return read_csv_rows(path), path
        raise RuntimeError(f"unsupported log file type: {path}")

    candidates = [
        model_dir / "training_log.jsonl",
        model_dir / "trainer_log_history.json",
        model_dir / "trainer_log_history.csv",
    ]

    latest_trainer_state = find_latest_checkpoint_trainer_state(model_dir)
    if latest_trainer_state is not None:
        candidates.append(latest_trainer_state)

    for path in candidates:
        if not path.exists():
            continue
        if path.suffix == ".jsonl":
            rows = read_jsonl(path)
        elif path.suffix == ".json":
            rows = read_json(path)
        elif path.suffix == ".csv":
            rows = read_csv_rows(path)
        else:
            continue
        if rows:
            return rows, path

    searched = "\n".join(str(path) for path in candidates)
    raise FileNotFoundError(f"no usable log file found under {model_dir}. searched:\n{searched}")


def moving_average(values: List[float], window: int) -> List[float]:
    if window <= 1 or len(values) <= 1:
        return values[:]

    out: List[float] = []
    acc = 0.0
    queue: List[float] = []
    for value in values:
        queue.append(value)
        acc += value
        if len(queue) > window:
            acc -= queue.pop(0)
        out.append(acc / len(queue))
    return out


def pick(rows: Iterable[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    return [row for row in rows if row.get(key) is not None]


def to_xy(rows: Iterable[Dict[str, Any]], key: str, x_key: str = "step") -> tuple[List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    for row in rows:
        x_value = row.get(x_key)
        value = row.get(key)
        if x_value is None or value is None:
            continue
        xs.append(float(x_value))
        ys.append(float(value))
    return xs, ys


def metric_signature(row: Dict[str, Any]) -> tuple[Any, ...]:
    eval_loss = row.get("eval_loss")
    eval_bleu = row.get("eval_bleu")
    return (
        round(float(eval_loss), 6) if eval_loss is not None else None,
        round(float(eval_bleu), 6) if eval_bleu is not None else None,
    )


def split_eval_rows(eval_rows: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    main_rows: List[Dict[str, Any]] = []
    repeat_rows: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for row in eval_rows:
        signature = metric_signature(row)
        if signature in seen:
            repeat_rows.append(row)
        else:
            main_rows.append(row)
            seen.add(signature)

    return main_rows, repeat_rows


def annotate_best(ax, x: float, y: float, text: str, color: str) -> None:
    ax.scatter([x], [y], color=color, s=60, zorder=5)
    ax.annotate(
        text,
        xy=(x, y),
        xytext=(8, 8),
        textcoords="offset points",
        fontsize=9,
        color=color,
        bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": color, "alpha": 0.85},
    )


def save_training_curves(rows: List[Dict[str, Any]], output_dir: Path, smooth_window: int, dpi: int) -> None:
    train_rows = pick(rows, "loss")
    eval_rows = pick(rows, "eval_loss")
    eval_rows_main, eval_rows_repeat = split_eval_rows(eval_rows)
    eval_loss_rows = eval_rows_main
    eval_bleu_rows = [row for row in eval_rows_main if row.get("eval_bleu") is not None]
    eval_bleu_repeat_rows = [row for row in eval_rows_repeat if row.get("eval_bleu") is not None]
    lr_rows = pick(rows, "learning_rate")
    grad_rows = pick(rows, "grad_norm")

    x_loss, y_loss = to_xy(train_rows, "loss", x_key="epoch")
    x_eval_loss, y_eval_loss = to_xy(eval_loss_rows, "eval_loss", x_key="epoch")
    x_eval_loss_repeat, y_eval_loss_repeat = to_xy(eval_rows_repeat, "eval_loss", x_key="epoch")
    x_bleu, y_bleu = to_xy(eval_bleu_rows, "eval_bleu", x_key="epoch")
    x_bleu_repeat, y_bleu_repeat = to_xy(eval_bleu_repeat_rows, "eval_bleu", x_key="epoch")
    x_lr, y_lr = to_xy(lr_rows, "learning_rate", x_key="epoch")
    x_grad, y_grad = to_xy(grad_rows, "grad_norm", x_key="epoch")

    fig, axes = plt.subplots(2, 3, figsize=(16, 9))

    ax = axes[0, 0]
    if x_loss:
        ax.plot(x_loss, y_loss, color="#9aa5b1", linewidth=1.2, alpha=0.6, label="训练损失")
        ax.plot(x_loss, moving_average(y_loss, smooth_window), color="#d9485f", linewidth=2.0, label=f"训练损失-滑动平均({smooth_window})")
    ax.set_title("训练损失曲线")
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("损失值")
    ax.grid(alpha=0.25)
    ax.legend()

    ax = axes[0, 1]
    if x_eval_loss:
        ax.plot(x_eval_loss, y_eval_loss, color="#1769aa", marker="o", linewidth=2.0, label="验证损失")
        best_idx = min(range(len(y_eval_loss)), key=lambda i: y_eval_loss[i])
        annotate_best(ax, x_eval_loss[best_idx], y_eval_loss[best_idx], f"epoch={x_eval_loss[best_idx]:.2f}", "#1769aa")
    if x_eval_loss_repeat:
        ax.scatter(x_eval_loss_repeat, y_eval_loss_repeat, color="#f08c00", marker="*", s=90, label="最佳模型复评")
    ax.set_title("验证损失曲线")
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("损失值")
    ax.grid(alpha=0.25)
    if x_eval_loss or x_eval_loss_repeat:
        ax.legend()

    ax = axes[0, 2]
    if x_bleu:
        ax.plot(x_bleu, y_bleu, color="#2b8a3e", marker="o", linewidth=2.0, label="验证 BLEU")
        best_idx = max(range(len(y_bleu)), key=lambda i: y_bleu[i])
        annotate_best(ax, x_bleu[best_idx], y_bleu[best_idx], f"epoch={x_bleu[best_idx]:.2f}", "#2b8a3e")
    if x_bleu_repeat:
        ax.scatter(x_bleu_repeat, y_bleu_repeat, color="#f08c00", marker="*", s=90, label="最佳模型复评")
    ax.set_title("BLEU 变化曲线")
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("BLEU")
    ax.grid(alpha=0.25)
    if x_bleu or x_bleu_repeat:
        ax.legend()

    ax = axes[1, 0]
    if x_lr:
        ax.plot(x_lr, y_lr, color="#f08c00", linewidth=2.0, label="学习率")
    ax.set_title("学习率变化曲线")
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("学习率")
    ax.grid(alpha=0.25)
    if x_lr:
        ax.legend()

    ax = axes[1, 1]
    if x_grad:
        ax.plot(x_grad, y_grad, color="#6f42c1", linewidth=1.6, label="梯度范数")
    ax.set_title("梯度范数变化曲线")
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("梯度范数")
    ax.grid(alpha=0.25)
    if x_grad:
        ax.legend()

    ax = axes[1, 2]
    if x_loss:
        ax.plot(x_loss, moving_average(y_loss, smooth_window), color="#d9485f", linewidth=2.0, label=f"训练损失-滑动平均({smooth_window})")
    if x_eval_loss:
        ax.plot(x_eval_loss, y_eval_loss, color="#1769aa", marker="o", linewidth=2.0, label="验证损失")
        best_idx = min(range(len(y_eval_loss)), key=lambda i: y_eval_loss[i])
        annotate_best(ax, x_eval_loss[best_idx], y_eval_loss[best_idx], f"最佳点\nepoch={x_eval_loss[best_idx]:.2f}", "#1769aa")
    if x_eval_loss_repeat:
        ax.scatter(x_eval_loss_repeat, y_eval_loss_repeat, color="#f08c00", marker="*", s=90, label="最佳模型复评")
    ax.set_title("训练/验证损失对比")
    ax.set_xlabel("训练轮次")
    ax.set_ylabel("损失值")
    ax.grid(alpha=0.25)
    if x_loss or x_eval_loss or x_eval_loss_repeat:
        ax.legend()

    fig.tight_layout()
    fig.savefig(output_dir / "training_curves.png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    if x_eval_loss or x_bleu:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

        ax = axes[0]
        if x_eval_loss:
            ax.plot(x_eval_loss, y_eval_loss, color="#1769aa", marker="o", linewidth=2.0, label="验证损失")
            best_idx = min(range(len(y_eval_loss)), key=lambda i: y_eval_loss[i])
            annotate_best(ax, x_eval_loss[best_idx], y_eval_loss[best_idx], f"epoch={x_eval_loss[best_idx]:.2f}", "#1769aa")
        if x_eval_loss_repeat:
            ax.scatter(x_eval_loss_repeat, y_eval_loss_repeat, color="#f08c00", marker="*", s=90, label="最佳模型复评")
        ax.set_title("验证损失放大图")
        ax.set_xlabel("训练轮次")
        ax.set_ylabel("损失值")
        ax.grid(alpha=0.25)
        if x_eval_loss or x_eval_loss_repeat:
            ax.legend()

        ax = axes[1]
        if x_bleu:
            ax.plot(x_bleu, y_bleu, color="#2b8a3e", marker="o", linewidth=2.0, label="验证 BLEU")
            best_idx = max(range(len(y_bleu)), key=lambda i: y_bleu[i])
            annotate_best(ax, x_bleu[best_idx], y_bleu[best_idx], f"epoch={x_bleu[best_idx]:.2f}", "#2b8a3e")
        if x_bleu_repeat:
            ax.scatter(x_bleu_repeat, y_bleu_repeat, color="#f08c00", marker="*", s=90, label="最佳模型复评")
        ax.set_title("验证 BLEU 放大图")
        ax.set_xlabel("训练轮次")
        ax.set_ylabel("BLEU")
        ax.grid(alpha=0.25)
        if x_bleu or x_bleu_repeat:
            ax.legend()

        fig.tight_layout()
        fig.savefig(output_dir / "eval_metrics_zoom.png", dpi=dpi, bbox_inches="tight")
        plt.close(fig)

    if x_loss or x_eval_loss:
        fig, ax = plt.subplots(figsize=(12, 5))
        if x_loss:
            ax.plot(x_loss, moving_average(y_loss, smooth_window), color="#d9485f", linewidth=2.0, label=f"训练损失-滑动平均({smooth_window})")
        if x_eval_loss:
            ax.plot(x_eval_loss, y_eval_loss, color="#1769aa", marker="o", linewidth=2.0, label="验证损失")
            best_idx = min(range(len(y_eval_loss)), key=lambda i: y_eval_loss[i])
            annotate_best(ax, x_eval_loss[best_idx], y_eval_loss[best_idx], f"最佳点 epoch={x_eval_loss[best_idx]:.2f}", "#1769aa")
        if x_eval_loss_repeat:
            ax.scatter(x_eval_loss_repeat, y_eval_loss_repeat, color="#f08c00", marker="*", s=90, label="最佳模型复评")
        ax.set_title("训练损失与验证损失对比")
        ax.set_xlabel("训练轮次")
        ax.set_ylabel("损失值")
        ax.grid(alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(output_dir / "loss_curve.png", dpi=dpi, bbox_inches="tight")
        plt.close(fig)


def summarize_best(rows: List[Dict[str, Any]], output_dir: Path) -> None:
    eval_rows = pick(rows, "eval_loss")
    eval_rows_main, eval_rows_repeat = split_eval_rows(eval_rows)
    eval_loss_rows = eval_rows_main
    eval_bleu_rows = [row for row in eval_rows_main if row.get("eval_bleu") is not None]

    summary: Dict[str, Any] = {
        "eval_points": {
            "main_count": len(eval_rows_main),
            "repeat_count": len(eval_rows_repeat),
        }
    }

    if eval_loss_rows:
        best_eval_loss = min(eval_loss_rows, key=lambda row: float(row["eval_loss"]))
        summary["best_eval_loss"] = {
            "step": int(best_eval_loss["step"]),
            "epoch": best_eval_loss.get("epoch"),
            "eval_loss": float(best_eval_loss["eval_loss"]),
        }

    if eval_bleu_rows:
        best_eval_bleu = max(eval_bleu_rows, key=lambda row: float(row["eval_bleu"]))
        summary["best_eval_bleu"] = {
            "step": int(best_eval_bleu["step"]),
            "epoch": best_eval_bleu.get("epoch"),
            "eval_bleu": float(best_eval_bleu["eval_bleu"]),
        }

    (output_dir / "curve_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> None:
    configure_matplotlib()
    args = parse_args()
    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        raise FileNotFoundError(f"model_dir not found: {model_dir}")

    rows, source_file = load_rows(model_dir, args.log_file)
    if not rows:
        raise RuntimeError(f"log file is empty: {source_file}")

    save_training_curves(rows, model_dir, args.smooth_window, args.dpi)
    summarize_best(rows, model_dir)
    print(f"[source] {source_file}")
    print(f"[saved] {model_dir / 'training_curves.png'}")
    print(f"[saved] {model_dir / 'loss_curve.png'}")
    print(f"[saved] {model_dir / 'eval_metrics_zoom.png'}")


if __name__ == "__main__":
    main()
