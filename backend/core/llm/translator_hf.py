# backend/core/llm/translator_hf.py

import os
import re
import threading
from typing import Dict, Tuple

try:
    import torch
    _TORCH_IMPORT_ERROR = None
except Exception as exc:
    torch = None
    _TORCH_IMPORT_ERROR = exc

AutoModelForSeq2SeqLM = None
AutoTokenizer = None
_TRANSFORMERS_IMPORT_ERROR = None
PeftModel = None
_PEFT_IMPORT_ERROR = None


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

MODEL_NAME = os.environ.get("NLLB_MODEL_PATH") or os.path.join(
    _BASE_DIR, "huggingface", "hub", "models--facebook--nllb-200-distilled-600M",
    "snapshots", "f8d333a098d19b4fd9a8b18f94170487ad3f821d",
)

LORA_MODEL_PATH = os.environ.get("LORA_ADAPTER_PATH") or os.path.join(
    _BASE_DIR, "scripts", "models", "nllb-medical-lora-optimized",
)

LANG_CODE_MAP: Dict[str, str] = {
    "zh": "zho_Hans",
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "ja": "jpn_Jpan",
}

_LOCK = threading.Lock()
_TOKENIZER = None
_MODEL = None


def _postprocess_translation(text: str, tgt_lang: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return text

    tgt = (tgt_lang or "").strip().lower()
    if tgt in {"zh", "ja"}:
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


def _import_transformers():
    global AutoModelForSeq2SeqLM, AutoTokenizer, _TRANSFORMERS_IMPORT_ERROR

    if AutoTokenizer is not None and AutoModelForSeq2SeqLM is not None:
        return

    try:
        from transformers import AutoModelForSeq2SeqLM as _AutoModelForSeq2SeqLM
        from transformers import AutoTokenizer as _AutoTokenizer
    except Exception as exc:
        _TRANSFORMERS_IMPORT_ERROR = exc
        raise RuntimeError(f"transformers is not available; translation model is unavailable ({exc})") from exc

    AutoModelForSeq2SeqLM = _AutoModelForSeq2SeqLM
    AutoTokenizer = _AutoTokenizer


def _import_peft():
    global PeftModel, _PEFT_IMPORT_ERROR

    if PeftModel is not None:
        return PeftModel

    if _PEFT_IMPORT_ERROR is not None:
        return None

    try:
        from peft import PeftModel as _PeftModel
    except Exception as exc:
        _PEFT_IMPORT_ERROR = exc
        return None

    PeftModel = _PeftModel
    return PeftModel


def _ensure_runtime_available():
    if torch is None:
        detail = f" ({_TORCH_IMPORT_ERROR})" if _TORCH_IMPORT_ERROR else ""
        raise RuntimeError(f"PyTorch is not installed; translation model is unavailable{detail}")

    _import_transformers()


def _load_model():
    global _TOKENIZER, _MODEL

    if _TOKENIZER is not None and _MODEL is not None:
        return

    with _LOCK:
        if _TOKENIZER is not None and _MODEL is not None:
            return

        _ensure_runtime_available()

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        print(f"[translator_hf] loading NLLB model: {MODEL_NAME}")

        _TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME, local_files_only=True)
        _MODEL = AutoModelForSeq2SeqLM.from_pretrained(
            MODEL_NAME,
            dtype=dtype,
            local_files_only=True,
        ).to(device)

        _MODEL.eval()
        _MODEL.generation_config.max_length = None
        print("[translator_hf] NLLB model loaded (single instance, LoRA attached on demand)")


def _load_lora_model():
    peft_model_cls = _import_peft()
    if peft_model_cls is None:
        return None

    if not os.path.exists(LORA_MODEL_PATH):
        return None

    _load_model()
    lora_model = peft_model_cls.from_pretrained(_MODEL, LORA_MODEL_PATH)
    lora_model.eval()
    return lora_model


def _normalize_lang(lang: str) -> str:
    return (lang or "").strip().lower()


def _get_nllb_lang_code(lang: str) -> str:
    lang = _normalize_lang(lang)
    code = LANG_CODE_MAP.get(lang)
    if not code:
        raise ValueError(f"Unsupported language: {lang}")
    return code


def translate(text: str, src_lang: str, tgt_lang: str, max_new_tokens: int = 256) -> str:
    result, _ = translate_with_lora(text, src_lang, tgt_lang, max_new_tokens)
    return result


def translate_with_lora(text: str, src_lang: str, tgt_lang: str, max_new_tokens: int = 256) -> Tuple[str, str]:
    text = (text or "").strip()
    if not text:
        return "", ""

    _load_model()

    src_code = _get_nllb_lang_code(src_lang)
    tgt_code = _get_nllb_lang_code(tgt_lang)

    tokenizer = _TOKENIZER
    device = next(_MODEL.parameters()).device

    tokenizer.src_lang = src_code

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512
    ).to(device)

    with torch.inference_mode():
        base_outputs = _MODEL.generate(
            **inputs,
            forced_bos_token_id=tokenizer.convert_tokens_to_ids(tgt_code),
            max_new_tokens=max_new_tokens,
            num_beams=4,
        )

    base_result = tokenizer.batch_decode(base_outputs, skip_special_tokens=True)[0].strip()
    base_result = _postprocess_translation(base_result, tgt_lang)

    lora_result = base_result
    lora_model = _load_lora_model()
    if lora_model is not None:
        with torch.inference_mode():
            lora_outputs = lora_model.generate(
                **inputs,
                forced_bos_token_id=tokenizer.convert_tokens_to_ids(tgt_code),
                max_new_tokens=max_new_tokens,
                num_beams=4,
            )
        lora_result = tokenizer.batch_decode(lora_outputs, skip_special_tokens=True)[0].strip()
        lora_result = _postprocess_translation(lora_result, tgt_lang)

    return base_result, lora_result


def translate_en_zh(text: str, max_new_tokens: int = 256) -> str:
    return translate(text=text, src_lang="en", tgt_lang="zh", max_new_tokens=max_new_tokens)


def translate_zh_en(text: str, max_new_tokens: int = 256) -> str:
    return translate(text=text, src_lang="zh", tgt_lang="en", max_new_tokens=max_new_tokens)
