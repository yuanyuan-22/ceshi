#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare one sentence across base NLLB and three local LoRA adapters.

Examples:
  python scripts/compare_nllb_four_models.py --text "The patient has diabetes mellitus." --direction en-zh
  python scripts/compare_nllb_four_models.py --text "患者患有糖尿病。" --src_lang zh --tgt_lang en
  python scripts/compare_nllb_four_models.py
"""

from __future__ import annotations

import argparse
import gc
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

torch = None
PeftModel = None
AutoModelForSeq2SeqLM = None
AutoTokenizer = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_MODEL = (
    ROOT
    / "huggingface"
    / "hub"
    / "models--facebook--nllb-200-distilled-600M"
    / "snapshots"
    / "f8d333a098d19b4fd9a8b18f94170487ad3f821d"
)

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

NLLB_TO_SHORT: Dict[str, str] = {
    "zho_Hans": "zh",
    "eng_Latn": "en",
    "fra_Latn": "fr",
    "deu_Latn": "de",
    "jpn_Jpan": "ja",
}


@dataclass(frozen=True)
class ModelSpec:
    name: str
    lora_path: Optional[Path] = None


@dataclass(frozen=True)
class TranslationResult:
    name: str
    output: str
    elapsed_seconds: float


MODEL_SPECS: Tuple[ModelSpec, ...] = (
    ModelSpec("base"),
    ModelSpec("nllb-medical-lora", ROOT / "scripts" / "models" / "nllb-medical-lora"),
    ModelSpec(
        "nllb-medical-lora-optimized",
        ROOT / "scripts" / "models" / "nllb-medical-lora-optimized",
    ),
    ModelSpec(
        "nllb-paramed-lora-1000-e20-b24",
        ROOT / "scripts" / "models" / "nllb-paramed-lora-1000-e20-b24",
    ),
)


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def ensure_runtime_available() -> None:
    global torch, PeftModel, AutoModelForSeq2SeqLM, AutoTokenizer

    if (
        torch is not None
        and PeftModel is not None
        and AutoModelForSeq2SeqLM is not None
        and AutoTokenizer is not None
    ):
        return

    errors: List[str] = []
    try:
        import torch as torch_module
    except Exception as exc:
        errors.append(f"torch: {exc}")
    else:
        torch = torch_module

    try:
        from peft import PeftModel as peft_model_cls
    except Exception as exc:
        errors.append(f"peft: {exc}")
    else:
        PeftModel = peft_model_cls

    try:
        from transformers import AutoModelForSeq2SeqLM as seq2seq_cls
        from transformers import AutoTokenizer as tokenizer_cls
    except Exception as exc:
        errors.append(f"transformers: {exc}")
    else:
        AutoModelForSeq2SeqLM = seq2seq_cls
        AutoTokenizer = tokenizer_cls

    if errors:
        detail = "; ".join(errors)
        raise RuntimeError(
            "Missing translation runtime dependencies. Run this script in the Python "
            f"environment that has torch, peft, and transformers installed. Details: {detail}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare base NLLB and local LoRA adapters on one input sentence.",
    )
    parser.add_argument("--text", type=str, default=None, help="Input sentence.")
    parser.add_argument(
        "--direction",
        type=str,
        default=None,
        help="Direction such as zh-en, en-zh, zh->en, or en->zh.",
    )
    parser.add_argument("--src_lang", type=str, default="zh", help="Source language.")
    parser.add_argument("--tgt_lang", type=str, default="en", help="Target language.")
    parser.add_argument("--base_model", type=str, default=str(DEFAULT_BASE_MODEL))
    parser.add_argument("--max_new_tokens", type=int, default=128)
    parser.add_argument("--num_beams", type=int, default=4)
    parser.add_argument(
        "--skip_missing",
        action="store_true",
        help="Skip missing LoRA folders instead of failing.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep asking for more sentences after the first interactive run.",
    )
    return parser.parse_args()


def normalize_short_lang(lang: str) -> str:
    key = (lang or "").strip().replace("-", "_").lower()
    if not key:
        raise ValueError("language is empty")
    if key in NLLB_TO_SHORT:
        return NLLB_TO_SHORT[key]
    if key in LANG_CODE_MAP:
        code = LANG_CODE_MAP[key]
        return NLLB_TO_SHORT.get(code, key)
    raise ValueError(f"Unsupported language: {lang}")


def to_nllb_code(lang: str) -> str:
    key = (lang or "").strip()
    if key in NLLB_TO_SHORT:
        return key
    short = normalize_short_lang(key)
    return LANG_CODE_MAP[short]


def parse_direction(direction: Optional[str], src_lang: str, tgt_lang: str) -> Tuple[str, str]:
    if not direction:
        return normalize_short_lang(src_lang), normalize_short_lang(tgt_lang)

    raw = direction.strip().lower()
    presets = {
        "1": ("zh", "en"),
        "2": ("en", "zh"),
        "zh-en": ("zh", "en"),
        "zh>en": ("zh", "en"),
        "zh->en": ("zh", "en"),
        "zh2en": ("zh", "en"),
        "en-zh": ("en", "zh"),
        "en>zh": ("en", "zh"),
        "en->zh": ("en", "zh"),
        "en2zh": ("en", "zh"),
    }
    if raw in presets:
        return presets[raw]

    pieces = re.split(r"\s+|,|/|->|>|-", raw)
    pieces = [piece for piece in pieces if piece]
    if len(pieces) != 2:
        raise ValueError(
            "Direction must look like 'zh-en', 'en-zh', 'zh->en', or use --src_lang/--tgt_lang."
        )
    return normalize_short_lang(pieces[0]), normalize_short_lang(pieces[1])


def postprocess_translation(text: str, tgt_lang: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return text

    tgt = normalize_short_lang(tgt_lang)
    if tgt in {"zh", "ja"}:
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        text = re.sub(r"\s*([\uFF0C\u3002\uFF01\uFF1F\uFF1B\uFF1A\u3001])", r"\1", text)
        text = re.sub(
            r"(?<=[\u3400-\u9fff\u3040-\u30ff])\s+(?=[\u3400-\u9fff\u3040-\u30ff])",
            "",
            text,
        )
        text = re.sub(
            r"(?<=[\u3400-\u9fff\u3040-\u30ff])\s+(?=[A-Za-z0-9])",
            "",
            text,
        )
        text = re.sub(
            r"(?<=[A-Za-z0-9])\s+(?=[\u3400-\u9fff\u3040-\u30ff])",
            "",
            text,
        )
        text = re.sub(r"\(\s+", "(", text)
        text = re.sub(r"\s+\)", ")", text)
        text = text.replace(".", "\u3002")
        text = text.replace(",", "\uFF0C")
        text = text.replace("?", "\uFF1F")
        text = text.replace("!", "\uFF01")
    else:
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        text = re.sub(r"\(\s+", "(", text)
        text = re.sub(r"\s+\)", ")", text)

    return text.strip()


def model_dtype() -> Tuple[str, object]:
    ensure_runtime_available()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    return device, dtype


def load_tokenizer(base_model: Path):
    ensure_runtime_available()
    return AutoTokenizer.from_pretrained(str(base_model), local_files_only=True)


def load_base_model(base_model: Path, device: str, dtype: object):
    ensure_runtime_available()
    try:
        model = AutoModelForSeq2SeqLM.from_pretrained(
            str(base_model),
            torch_dtype=dtype,
            local_files_only=True,
        ).to(device)
    except TypeError as exc:
        if "torch_dtype" not in str(exc) and "unexpected keyword" not in str(exc):
            raise
        model = AutoModelForSeq2SeqLM.from_pretrained(
            str(base_model),
            dtype=dtype,
            local_files_only=True,
        ).to(device)
    model.generation_config.max_length = None
    model.eval()
    return model


def translate_once(
    model,
    tokenizer,
    text: str,
    src_lang: str,
    tgt_lang: str,
    max_new_tokens: int,
    num_beams: int,
) -> str:
    ensure_runtime_available()
    src_code = to_nllb_code(src_lang)
    tgt_code = to_nllb_code(tgt_lang)
    tokenizer.src_lang = src_code
    device = next(model.parameters()).device
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
    ).to(device)

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.convert_tokens_to_ids(tgt_code),
            max_new_tokens=max_new_tokens,
            num_beams=num_beams,
        )
    decoded = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0].strip()
    return postprocess_translation(decoded, tgt_lang)


def release_memory() -> None:
    gc.collect()
    if torch is None:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def validate_paths(base_model: Path, specs: Iterable[ModelSpec], skip_missing: bool) -> List[ModelSpec]:
    if not base_model.exists():
        raise FileNotFoundError(f"Base model not found: {base_model}")

    usable: List[ModelSpec] = []
    for spec in specs:
        if spec.lora_path is None:
            usable.append(spec)
            continue
        if spec.lora_path.exists():
            usable.append(spec)
        elif skip_missing:
            print(f"[skip] {spec.name}: missing folder {spec.lora_path}")
        else:
            raise FileNotFoundError(f"LoRA adapter not found for {spec.name}: {spec.lora_path}")
    return usable


def run_model(
    spec: ModelSpec,
    base_model: Path,
    text: str,
    src_lang: str,
    tgt_lang: str,
    max_new_tokens: int,
    num_beams: int,
) -> TranslationResult:
    ensure_runtime_available()
    device, dtype = model_dtype()
    print(f"[load] {spec.name} on {device}")
    start = time.perf_counter()

    tokenizer = load_tokenizer(base_model)
    base = load_base_model(base_model, device, dtype)
    if spec.lora_path is None:
        model = base
    else:
        model = PeftModel.from_pretrained(base, str(spec.lora_path)).to(device)
        model.generation_config.max_length = None
        model.eval()

    try:
        output = translate_once(
            model,
            tokenizer,
            text,
            src_lang,
            tgt_lang,
            max_new_tokens,
            num_beams,
        )
    finally:
        del model
        del base
        del tokenizer
        release_memory()

    elapsed = time.perf_counter() - start
    return TranslationResult(spec.name, output, elapsed)


def compare_once(args: argparse.Namespace, text: str, src_lang: str, tgt_lang: str) -> None:
    ensure_runtime_available()
    base_model = Path(args.base_model).resolve()
    specs = validate_paths(base_model, MODEL_SPECS, args.skip_missing)

    print("=" * 100)
    print(f"Input     : {text}")
    print(f"Direction : {src_lang} -> {tgt_lang}")
    print(f"Base model: {base_model}")
    print("=" * 100)

    results: List[TranslationResult] = []
    for spec in specs:
        result = run_model(
            spec,
            base_model,
            text,
            src_lang,
            tgt_lang,
            args.max_new_tokens,
            args.num_beams,
        )
        results.append(result)
        print(f"[done] {result.name}: {result.elapsed_seconds:.2f}s")

    print("\nResults")
    print("-" * 100)
    for result in results:
        print(f"[{result.name}] ({result.elapsed_seconds:.2f}s)")
        print(result.output)
        print("-" * 100)


def prompt_direction(default_src: str, default_tgt: str) -> Tuple[str, str]:
    print("Choose direction:")
    print("  1. zh -> en")
    print("  2. en -> zh")
    print(f"  Enter custom, for example: fr-en. Empty uses {default_src}->{default_tgt}.")
    value = input("direction: ").strip()
    return parse_direction(value or None, default_src, default_tgt)


def prompt_text() -> str:
    return input("text: ").strip()


def main() -> None:
    configure_stdout()
    args = parse_args()

    if args.text:
        src_lang, tgt_lang = parse_direction(args.direction, args.src_lang, args.tgt_lang)
        compare_once(args, args.text.strip(), src_lang, tgt_lang)
        return

    while True:
        src_lang, tgt_lang = prompt_direction(args.src_lang, args.tgt_lang)
        text = prompt_text()
        if not text:
            print("Empty text, exit.")
            return
        compare_once(args, text, src_lang, tgt_lang)
        if not args.loop:
            return


if __name__ == "__main__":
    main()
