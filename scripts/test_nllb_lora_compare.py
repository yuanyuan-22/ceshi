#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比原始 NLLB 基座模型与 LoRA 医疗模型的翻译效果（升级版）。

支持：
1. 内置样例测试
2. 从 jsonl 测试文件读取（term_eval_pairs.jsonl / sentence_eval_pairs.jsonl）
3. strict_hit（整句严格命中）
4. term_hit（关键医学术语命中）
5. 输出详细结果 jsonl + 汇总 summary json

推荐用法：

1）术语评测
python ./scripts/test_nllb_lora_compare.py `
  --base_model "./huggingface/hub/models--facebook--nllb-200-distilled-600M/snapshots/f8d333a098d19b4fd9a8b18f94170487ad3f821d" `
  --lora_model "./scripts/models/nllb-medical-lora-optimized" `
  --test_file "./backend/data/nllb/term_eval_pairs.jsonl" `
  --save_path "./scripts/models/nllb-medical-lora/term_compare_results.jsonl" `
  --summary_path "./scripts/models/nllb-medical-lora/term_compare_summary.json"

linux
python ./scripts/test_nllb_lora_compare.py \
  --base_model "./huggingface/hub/models--facebook--nllb-200-distilled-600M/snapshots/f8d333a098d19b4fd9a8b18f94170487ad3f821d" \
  --lora_model "./scripts/models/nllb-medical-lora" \
  --test_file "./backend/data/nllb/term_eval_pairs.jsonl" \
  --save_path "./scripts/models/nllb-medical-lora/term_compare_results.jsonl" \
  --summary_path "./scripts/models/nllb-medical-lora/term_compare_summary.json"
"""

from __future__ import annotations

import argparse
import json
import re
import string
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
from peft import PeftModel
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


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

NLLB_TO_SHORT = {
    "zho_Hans": "zh",
    "eng_Latn": "en",
    "fra_Latn": "fr",
    "deu_Latn": "de",
    "jpn_Jpan": "ja",
}

DEFAULT_CASES = [
    {"src_text": "高血压", "src_lang": "zh", "tgt_lang": "en", "reference": "Hypertension", "sample_type": "manual", "eval_type": "term"},
    {"src_text": "糖尿病", "src_lang": "zh", "tgt_lang": "en", "reference": "Diabetes mellitus", "sample_type": "manual", "eval_type": "term"},
    {"src_text": "支气管哮喘", "src_lang": "zh", "tgt_lang": "en", "reference": "Bronchial asthma", "sample_type": "manual", "eval_type": "term"},
    {"src_text": "患者患有糖尿病和高血压。", "src_lang": "zh", "tgt_lang": "en", "reference": "The patient has diabetes mellitus and hypertension.", "sample_type": "manual", "eval_type": "sentence"},
    {"src_text": "建议监测血压并规律服药。", "src_lang": "zh", "tgt_lang": "en", "reference": "Blood pressure monitoring and regular medication are recommended.", "sample_type": "manual", "eval_type": "sentence"},
    {"src_text": "Hypertension", "src_lang": "en", "tgt_lang": "zh", "reference": "高血压", "sample_type": "manual", "eval_type": "term"},
    {"src_text": "Diabetes mellitus", "src_lang": "en", "tgt_lang": "zh", "reference": "糖尿病", "sample_type": "manual", "eval_type": "term"},
    {"src_text": "The patient has diabetes and high blood pressure.", "src_lang": "en", "tgt_lang": "zh", "reference": "患者患有糖尿病和高血压。", "sample_type": "manual", "eval_type": "sentence"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base_model", type=str, required=True, help="NLLB 基座模型路径")
    parser.add_argument("--lora_model", type=str, required=True, help="LoRA 适配器目录")
    parser.add_argument("--src_lang", type=str, default=None, help="仅测试该源语言，例如 zh")
    parser.add_argument("--tgt_lang", type=str, default=None, help="仅测试该目标语言，例如 en")
    parser.add_argument("--test_file", type=str, default=None, help="可选，jsonl 测试文件")
    parser.add_argument("--max_cases", type=int, default=100000, help="从 test_file 最多读取多少条")
    parser.add_argument("--max_new_tokens", type=int, default=128)
    parser.add_argument("--num_beams", type=int, default=4)
    parser.add_argument("--save_path", type=str, default=None, help="可选，保存详细结果到 jsonl")
    parser.add_argument("--summary_path", type=str, default=None, help="可选，保存汇总统计到 json")
    parser.add_argument("--merge_and_save", type=str, default=None, help="可选，将 LoRA 合并后模型另存到该目录")
    parser.add_argument("--quiet", action="store_true", help="安静模式，减少逐条打印")
    return parser.parse_args()


def normalize_lang(lang: str) -> str:
    lang = (lang or "").strip()
    if not lang:
        raise ValueError("language is empty")

    lower = lang.lower()
    if lower in LANG_CODE_MAP:
        return NLLB_TO_SHORT.get(LANG_CODE_MAP[lower], lower if lower in {"zh", "en", "fr", "de", "ja"} else lower)

    if lang in NLLB_TO_SHORT:
        return NLLB_TO_SHORT[lang]

    raise ValueError(f"Unsupported language: {lang}")


def to_nllb_code(lang: str) -> str:
    lang = (lang or "").strip()
    if lang in NLLB_TO_SHORT:
        return lang
    lower = lang.lower()
    if lower in LANG_CODE_MAP:
        return LANG_CODE_MAP[lower]
    raise ValueError(f"Unsupported language: {lang}")


def normalize_text_basic(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def postprocess_translation(text: str, tgt_lang: str) -> str:
    text = normalize_text_basic(text)
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


def normalize_for_strict_compare(text: str) -> str:
    text = normalize_text_basic(text)
    text = text.lower()
    text = text.replace("，", ",").replace("。", ".").replace("；", ";").replace("：", ":")
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    # 去掉句末中英文标点差异影响
    text = re.sub(r"[.!?。！？]+$", "", text)
    return text.strip()


def tokenize_en_like(text: str) -> List[str]:
    text = normalize_for_strict_compare(text)
    table = str.maketrans("", "", string.punctuation)
    text = text.translate(table)
    toks = [x for x in text.split() if x]
    return toks


def contains_zh_term(text: str, term: str) -> bool:
    return normalize_text_basic(term) in normalize_text_basic(text)


def contains_en_term(text: str, term: str) -> bool:
    text_norm = " " + normalize_for_strict_compare(text) + " "
    term_norm = " " + normalize_for_strict_compare(term) + " "
    return term_norm in text_norm


def read_jsonl(path: str, max_cases: int) -> List[Dict]:
    items: List[Dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
            if len(items) >= max_cases:
                break
    return items


def infer_eval_type(x: Dict) -> str:
    if x.get("eval_type"):
        return str(x["eval_type"])
    if x.get("sample_type") in {"term", "alias_term", "term_normalization"}:
        return "term"
    return "sentence"


def load_cases(args: argparse.Namespace) -> List[Dict]:
    if args.test_file:
        cases = read_jsonl(args.test_file, args.max_cases)
    else:
        cases = DEFAULT_CASES.copy()

    filtered: List[Dict] = []
    for x in cases:
        src_lang = normalize_lang(x.get("src_lang", args.src_lang or "zh"))
        tgt_lang = normalize_lang(x.get("tgt_lang", args.tgt_lang or "en"))

        if args.src_lang and src_lang != normalize_lang(args.src_lang):
            continue
        if args.tgt_lang and tgt_lang != normalize_lang(args.tgt_lang):
            continue

        filtered.append(
            {
                "src_text": x["src_text"],
                "reference": x.get("tgt_text") or x.get("reference", ""),
                "src_lang": src_lang,
                "tgt_lang": tgt_lang,
                "sample_type": x.get("sample_type", "manual"),
                "eval_type": infer_eval_type(x),
                "entity_id": x.get("entity_id"),
                "canonical_key": x.get("canonical_key"),
                "category": x.get("category"),
                "meta": x.get("meta", {}),
            }
        )
    return filtered


class Translator:
    def __init__(self, model, tokenizer):
        self.model = model
        self.tokenizer = tokenizer
        self.device = next(model.parameters()).device

    def translate(self, text: str, src_lang: str, tgt_lang: str, max_new_tokens: int, num_beams: int) -> str:
        src_code = to_nllb_code(src_lang)
        tgt_code = to_nllb_code(tgt_lang)
        self.tokenizer.src_lang = src_code
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(self.device)
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(tgt_code),
                max_new_tokens=max_new_tokens,
                num_beams=num_beams,
            )
        decoded = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)[0].strip()
        return postprocess_translation(decoded, tgt_lang)


def load_base_translator(base_model: str) -> Translator:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(
        base_model,
        dtype=dtype,
        local_files_only=True
    ).to(device)
    model.generation_config.max_length = None
    model.eval()
    return Translator(model, tokenizer)


def load_lora_translator(base_model: str, lora_model: str) -> Translator:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    base = AutoModelForSeq2SeqLM.from_pretrained(
        base_model,
        dtype=dtype,
        local_files_only=True
    )
    model = PeftModel.from_pretrained(base, lora_model).to(device)
    model.generation_config.max_length = None
    model.eval()
    return Translator(model, tokenizer)


def strict_hit(pred: str, ref: str) -> int:
    if not ref:
        return -1
    return int(normalize_for_strict_compare(pred) == normalize_for_strict_compare(ref))


def extract_key_terms(ref: str, tgt_lang: str) -> List[str]:
    """
    从 reference 中提取关键术语：
    - 中文：简单基于常见病名/短语片段，按字符直接匹配
    - 英文：按 1~3gram 候选，从句中抽更像术语的片段
    """
    ref = normalize_text_basic(ref)
    if not ref:
        return []

    if tgt_lang == "zh":
        # 中文这里不做复杂分词，直接抓较明显医学短语
        candidates = re.findall(r"[\u4e00-\u9fffA-Za-z]{2,20}", ref)
        stop = {"患者", "建议", "监测", "规律", "服药", "既往", "病史", "考虑", "进一步", "检查", "明确", "存在"}
        terms = []
        for c in candidates:
            if c in stop:
                continue
            # 更偏术语的中文短语
            if len(c) >= 2:
                terms.append(c)
        # 去重保序
        dedup = []
        seen = set()
        for t in terms:
            if t not in seen:
                seen.add(t)
                dedup.append(t)
        return dedup

    # 英文
    toks = tokenize_en_like(ref)
    if not toks:
        return []

    stop = {
        "the", "a", "an", "patient", "has", "have", "with", "and", "or", "is", "are", "was", "were",
        "of", "for", "to", "there", "history", "recommended", "monitoring", "regular", "medication",
        "further", "evaluation", "considered", "suspected", "includes", "medical"
    }
    candidates: List[str] = []
    n = len(toks)

    # 先放 3-gram, 再 2-gram, 再 1-gram
    for gram in (3, 2, 1):
        for i in range(n - gram + 1):
            phrase = toks[i:i+gram]
            if all(w in stop for w in phrase):
                continue
            # 至少有一个非停用词
            joined = " ".join(phrase)
            candidates.append(joined)

    # 优先保留更像医学术语的短语
    preferred = []
    for c in candidates:
        if any(k in c for k in [
            "hypertension", "diabetes mellitus", "diabetes", "asthma", "bronchial asthma",
            "blood pressure", "glucose", "insulin", "metformin", "coronary heart disease",
            "pneumonia"
        ]):
            preferred.append(c)

    terms = preferred if preferred else candidates[:10]

    dedup = []
    seen = set()
    for t in terms:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup[:8]


def term_hit(pred: str, ref: str, tgt_lang: str, eval_type: str) -> Tuple[int, List[str], List[str]]:
    """
    term 评测：
    - 对术语类样本：要求 reference 术语命中
    - 对句子类样本：要求关键术语至少命中一个；若 reference 中可提取到多个明显术语，则尽量全部命中
    """
    if not ref:
        return -1, [], []

    terms = extract_key_terms(ref, tgt_lang)
    if not terms:
        # 回退：没有提取出术语时，用 strict 结果代替
        score = strict_hit(pred, ref)
        return score, [], []

    hits = []
    misses = []

    for t in terms:
        ok = contains_zh_term(pred, t) if tgt_lang == "zh" else contains_en_term(pred, t)
        if ok:
            hits.append(t)
        else:
            misses.append(t)

    if eval_type == "term":
        # 单术语测试更严格：至少 reference 术语本体要出现
        score = int(len(hits) >= 1 and len(misses) == 0)
    else:
        # 句子测试：只要关键术语多数命中即可。
        # 若术语数 <=2，要求全部命中；否则要求命中至少 2 个且命中率 >= 0.6
        if len(terms) <= 2:
            score = int(len(misses) == 0)
        else:
            hit_ratio = len(hits) / max(len(terms), 1)
            score = int(len(hits) >= 2 and hit_ratio >= 0.6)

    return score, hits, misses


def print_result_row(i: int, item: Dict):
    print("=" * 110)
    print(f"[{i}] {item['src_lang']} -> {item['tgt_lang']} | type={item['sample_type']} | eval={item['eval_type']}")
    print(f"SRC         : {item['src_text']}")
    if item.get("reference"):
        print(f"REF         : {item['reference']}")
    print(f"BASE        : {item['base_output']}")
    print(f"LORA        : {item['lora_output']}")
    print(f"BASE_STRICT : {item['base_strict_hit']}")
    print(f"LORA_STRICT : {item['lora_strict_hit']}")
    print(f"BASE_TERM   : {item['base_term_hit']}")
    print(f"LORA_TERM   : {item['lora_term_hit']}")
    if item.get("base_term_misses"):
        print(f"BASE_MISS   : {item['base_term_misses']}")
    if item.get("lora_term_misses"):
        print(f"LORA_MISS   : {item['lora_term_misses']}")
    print(f"CHANGE      : {'changed' if item['lora_output'] != item['base_output'] else 'same'}")


def maybe_merge_and_save(base_model: str, lora_model: str, save_dir: str):
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)
    base = AutoModelForSeq2SeqLM.from_pretrained(base_model, dtype=dtype, local_files_only=True)
    model = PeftModel.from_pretrained(base, lora_model)
    merged = model.merge_and_unload()
    merged.save_pretrained(save_path)
    tokenizer.save_pretrained(save_path)
    print(f"Merged model saved to: {save_path}")


def ratio_str(hit: int, total: int) -> str:
    if total <= 0:
        return "N/A"
    return f"{hit}/{total} = {hit / total:.2%}"


def summarize_results(results: List[Dict]) -> Dict:
    def build_bucket(rows: List[Dict]) -> Dict:
        strict_total = sum(1 for x in rows if x["base_strict_hit"] != -1)
        term_total = sum(1 for x in rows if x["base_term_hit"] != -1)

        base_strict = sum(1 for x in rows if x["base_strict_hit"] == 1)
        lora_strict = sum(1 for x in rows if x["lora_strict_hit"] == 1)
        base_term = sum(1 for x in rows if x["base_term_hit"] == 1)
        lora_term = sum(1 for x in rows if x["lora_term_hit"] == 1)

        return {
            "count": len(rows),
            "strict_total": strict_total,
            "base_strict_hit": base_strict,
            "lora_strict_hit": lora_strict,
            "strict_delta": lora_strict - base_strict,
            "strict_base_rate": (base_strict / strict_total) if strict_total else None,
            "strict_lora_rate": (lora_strict / strict_total) if strict_total else None,
            "term_total": term_total,
            "base_term_hit": base_term,
            "lora_term_hit": lora_term,
            "term_delta": lora_term - base_term,
            "term_base_rate": (base_term / term_total) if term_total else None,
            "term_lora_rate": (lora_term / term_total) if term_total else None,
        }

    summary = {
        "overall": build_bucket(results),
        "by_eval_type": {},
        "by_sample_type": {},
        "by_lang_direction": {},
    }

    by_eval_type = defaultdict(list)
    by_sample_type = defaultdict(list)
    by_lang_direction = defaultdict(list)

    for r in results:
        by_eval_type[r["eval_type"]].append(r)
        by_sample_type[r["sample_type"]].append(r)
        by_lang_direction[f"{r['src_lang']}->{r['tgt_lang']}"].append(r)

    for k, v in by_eval_type.items():
        summary["by_eval_type"][k] = build_bucket(v)
    for k, v in by_sample_type.items():
        summary["by_sample_type"][k] = build_bucket(v)
    for k, v in by_lang_direction.items():
        summary["by_lang_direction"][k] = build_bucket(v)

    # 只保留 LoRA 改变但 strict 或 term 没变好的失败样本计数
    summary["error_analysis"] = {
        "changed_outputs": sum(1 for x in results if x["base_output"] != x["lora_output"]),
        "lora_better_strict": sum(1 for x in results if x["lora_strict_hit"] > x["base_strict_hit"]),
        "lora_better_term": sum(1 for x in results if x["lora_term_hit"] > x["base_term_hit"]),
        "lora_worse_strict": sum(1 for x in results if x["lora_strict_hit"] < x["base_strict_hit"]),
        "lora_worse_term": sum(1 for x in results if x["lora_term_hit"] < x["base_term_hit"]),
    }

    return summary


def print_summary(summary: Dict):
    overall = summary["overall"]
    print("=" * 110)
    print("SUMMARY")
    print(f"Total cases         : {overall['count']}")
    print(f"Strict base         : {ratio_str(overall['base_strict_hit'], overall['strict_total'])}")
    print(f"Strict lora         : {ratio_str(overall['lora_strict_hit'], overall['strict_total'])}")
    print(f"Strict delta        : {overall['strict_delta']:+d}")
    print(f"Term base           : {ratio_str(overall['base_term_hit'], overall['term_total'])}")
    print(f"Term lora           : {ratio_str(overall['lora_term_hit'], overall['term_total'])}")
    print(f"Term delta          : {overall['term_delta']:+d}")

    print("-" * 110)
    print("BY EVAL TYPE")
    for k, v in summary["by_eval_type"].items():
        print(
            f"{k:24s} | count={v['count']:4d} "
            f"| strict {ratio_str(v['base_strict_hit'], v['strict_total'])} -> {ratio_str(v['lora_strict_hit'], v['strict_total'])} "
            f"| term {ratio_str(v['base_term_hit'], v['term_total'])} -> {ratio_str(v['lora_term_hit'], v['term_total'])}"
        )

    print("-" * 110)
    print("BY LANG DIRECTION")
    for k, v in summary["by_lang_direction"].items():
        print(
            f"{k:12s} | count={v['count']:4d} "
            f"| strict {ratio_str(v['base_strict_hit'], v['strict_total'])} -> {ratio_str(v['lora_strict_hit'], v['strict_total'])} "
            f"| term {ratio_str(v['base_term_hit'], v['term_total'])} -> {ratio_str(v['lora_term_hit'], v['term_total'])}"
        )


def main() -> None:
    args = parse_args()
    cases = load_cases(args)
    if not cases:
        raise SystemExit("没有可测试的样本，请检查 --src_lang/--tgt_lang 或 test_file。")

    print("Loading base model...")
    base_translator = load_base_translator(args.base_model)
    print("Loading LoRA model...")
    lora_translator = load_lora_translator(args.base_model, args.lora_model)

    results: List[Dict] = []

    for i, case in enumerate(cases, start=1):
        base_out = base_translator.translate(
            case["src_text"], case["src_lang"], case["tgt_lang"], args.max_new_tokens, args.num_beams
        )
        lora_out = lora_translator.translate(
            case["src_text"], case["src_lang"], case["tgt_lang"], args.max_new_tokens, args.num_beams
        )

        base_strict = strict_hit(base_out, case.get("reference", ""))
        lora_strict = strict_hit(lora_out, case.get("reference", ""))

        base_term, base_hits, base_misses = term_hit(
            base_out, case.get("reference", ""), case["tgt_lang"], case["eval_type"]
        )
        lora_term, lora_hits, lora_misses = term_hit(
            lora_out, case.get("reference", ""), case["tgt_lang"], case["eval_type"]
        )

        item = {
            **case,
            "base_output": base_out,
            "lora_output": lora_out,
            "base_strict_hit": base_strict,
            "lora_strict_hit": lora_strict,
            "base_term_hit": base_term,
            "lora_term_hit": lora_term,
            "base_term_hits": base_hits,
            "base_term_misses": base_misses,
            "lora_term_hits": lora_hits,
            "lora_term_misses": lora_misses,
        }
        results.append(item)

        if not args.quiet:
            print_result_row(i, item)

    summary = summarize_results(results)
    print_summary(summary)

    if args.save_path:
        save_path = Path(args.save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            for row in results:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Saved detailed results to: {save_path}")

    if args.summary_path:
        summary_path = Path(args.summary_path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"Saved summary to: {summary_path}")

    if args.merge_and_save:
        maybe_merge_and_save(args.base_model, args.lora_model, args.merge_and_save)


if __name__ == "__main__":
    main()
