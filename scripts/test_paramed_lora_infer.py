#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal inference script for NLLB + LoRA medical translation.

Examples:
  python scripts/test_paramed_lora_infer.py --text "高血压患者需要长期监测血压。" --src_lang zh --tgt_lang en

  python scripts/test_paramed_lora_infer.py --interactive

  python scripts/test_paramed_lora_infer.py --show_base
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List

import torch
from peft import PeftModel
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_MODEL = ROOT / "huggingface" / "hub" / "models--facebook--nllb-200-distilled-600M" / "snapshots" / "f8d333a098d19b4fd9a8b18f94170487ad3f821d"
DEFAULT_LORA_MODEL = ROOT / "scripts" / "models" / "nllb-paramed-lora-1000-e20-b24"

LANG_CODE_MAP: Dict[str, str] = {
    "zh": "zho_Hans",
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "ja": "jpn_Jpan",
    "zho_hans": "zho_Hans",
    "eng_latn": "eng_Latn",
    "fra_latn": "fra_Latn",
    "deu_latn": "deu_Latn",
    "jpn_jpan": "jpn_Jpan",
}

SAMPLE_CASES: List[Dict[str, str]] = [
    {"src_lang": "zh", "tgt_lang": "en", "text": "高血压患者需要长期监测血压。"},
    {"src_lang": "zh", "tgt_lang": "en", "text": "建议继续服用二甲双胍，并定期复查血糖。"},
    {"src_lang": "en", "tgt_lang": "zh", "text": "The patient has diabetes mellitus and mild hypertension."},
    {"src_lang": "zh", "tgt_lang": "fr", "text": "该药物可用于缓解支气管哮喘症状。"},
    {"src_lang": "de", "tgt_lang": "zh", "text": "Der Patient klagt über Brustschmerzen und Schwindel."},
    {"src_lang": "ja", "tgt_lang": "en", "text": "患者は高血圧と糖尿病の既往があります。"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base_model", type=str, default=str(DEFAULT_BASE_MODEL))
    parser.add_argument("--lora_model", type=str, default=str(DEFAULT_LORA_MODEL))
    parser.add_argument("--text", type=str, default=None, help="Text to translate.")
    parser.add_argument("--src_lang", type=str, default="zh")
    parser.add_argument("--tgt_lang", type=str, default="en")
    parser.add_argument("--max_new_tokens", type=int, default=128)
    parser.add_argument("--num_beams", type=int, default=4)
    parser.add_argument("--show_base", action="store_true", help="Also print base-model output for comparison.")
    parser.add_argument("--interactive", action="store_true", help="Interactive CLI mode.")
    return parser.parse_args()


def normalize_lang(lang: str) -> str:
    lang = (lang or "").strip()
    if not lang:
        raise ValueError("language is empty")
    key = lang.lower()
    if key not in LANG_CODE_MAP:
        raise ValueError(f"unsupported language: {lang}")
    return LANG_CODE_MAP[key]


def postprocess_translation(text: str, tgt_lang: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return text

    tgt = (tgt_lang or "").strip().lower()
    if tgt in {"zh", "ja", "zho_hans", "jpn_jpan"}:
        text = re.sub(r"\s*([,.!?;:])", r"\1", text)
        text = re.sub(r"\s*([，。！？；：、])", r"\1", text)
        text = re.sub(r"(?<=[\u3400-\u9fff\u3040-\u30ff])\s+(?=[\u3400-\u9fff\u3040-\u30ff])", "", text)
        text = re.sub(r"(?<=[\u3400-\u9fff\u3040-\u30ff])\s+(?=[A-Za-z0-9])", "", text)
        text = re.sub(r"(?<=[A-Za-z0-9])\s+(?=[\u3400-\u9fff\u3040-\u30ff])", "", text)
        text = re.sub(r"\(\s+", "(", text)
        text = re.sub(r"\s+\)", ")", text)
        text = text.replace(".", "。").replace(",", "，").replace("?", "？").replace("!", "！")
    else:
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        text = re.sub(r"\(\s+", "(", text)
        text = re.sub(r"\s+\)", ")", text)

    return text.strip()


class Translator:
    def __init__(self, model, tokenizer):
        self.model = model
        self.tokenizer = tokenizer
        self.device = next(model.parameters()).device

    def translate(self, text: str, src_lang: str, tgt_lang: str, max_new_tokens: int, num_beams: int) -> str:
        src_code = normalize_lang(src_lang)
        tgt_code = normalize_lang(tgt_lang)
        self.tokenizer.src_lang = src_code
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        ).to(self.device)

        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(tgt_code),
                max_new_tokens=max_new_tokens,
                num_beams=num_beams,
            )
        decoded = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)[0].strip()
        return postprocess_translation(decoded, tgt_lang)


def load_translator(base_model: str, lora_model: str) -> Translator:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    base = AutoModelForSeq2SeqLM.from_pretrained(
        base_model,
        dtype=dtype,
        local_files_only=True,
    )
    model = PeftModel.from_pretrained(base, lora_model).to(device)
    model.generation_config.max_length = None
    model.eval()
    return Translator(model, tokenizer)


def load_base_translator(base_model: str) -> Translator:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(
        base_model,
        dtype=dtype,
        local_files_only=True,
    ).to(device)
    model.generation_config.max_length = None
    model.eval()
    return Translator(model, tokenizer)


def print_case_result(index: int, case: Dict[str, str], lora_translator: Translator, args: argparse.Namespace, base_translator: Translator | None) -> None:
    print("=" * 100)
    print(f"[{index}] {case['src_lang']} -> {case['tgt_lang']}")
    print(f"SRC : {case['text']}")
    if base_translator is not None:
        base_out = base_translator.translate(
            case["text"],
            case["src_lang"],
            case["tgt_lang"],
            args.max_new_tokens,
            args.num_beams,
        )
        print(f"BASE: {base_out}")
    lora_out = lora_translator.translate(
        case["text"],
        case["src_lang"],
        case["tgt_lang"],
        args.max_new_tokens,
        args.num_beams,
    )
    print(f"LORA: {lora_out}")


def run_interactive(args: argparse.Namespace, lora_translator: Translator, base_translator: Translator | None) -> None:
    print("Interactive mode. Empty text or 'exit' to quit.")
    while True:
        src_lang = input(f"src_lang [{args.src_lang}]: ").strip() or args.src_lang
        tgt_lang = input(f"tgt_lang [{args.tgt_lang}]: ").strip() or args.tgt_lang
        text = input("text: ").strip()
        if not text or text.lower() == "exit":
            break

        case = {"src_lang": src_lang, "tgt_lang": tgt_lang, "text": text}
        print_case_result(1, case, lora_translator, args, base_translator)


def main() -> None:
    args = parse_args()

    base_model = Path(args.base_model)
    lora_model = Path(args.lora_model)
    if not base_model.exists():
        raise FileNotFoundError(f"base model not found: {base_model}")
    if not lora_model.exists():
        raise FileNotFoundError(f"LoRA adapter not found: {lora_model}")

    print(f"[load] base model : {base_model}")
    print(f"[load] lora model : {lora_model}")
    lora_translator = load_translator(str(base_model), str(lora_model))
    base_translator = load_base_translator(str(base_model)) if args.show_base else None

    if args.interactive:
        run_interactive(args, lora_translator, base_translator)
        return

    if args.text:
        cases = [{"src_lang": args.src_lang, "tgt_lang": args.tgt_lang, "text": args.text}]
    else:
        cases = SAMPLE_CASES

    for index, case in enumerate(cases, start=1):
        print_case_result(index, case, lora_translator, args, base_translator)


if __name__ == "__main__":
    main()
