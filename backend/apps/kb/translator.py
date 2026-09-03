#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Dict, List

_DEMO_MOD = None
_DEMO_LOAD_ATTEMPTED = False


def _candidate_demo_paths() -> List[Path]:
    current = Path(__file__).resolve()
    backend_dir = current.parents[2]
    root_dir = current.parents[3]
    return [
        backend_dir / "data" / "kb_raw" / "apidemo" / "TranslateDemo_auto.py",
        root_dir / "backend" / "data" / "kb_raw" / "apidemo" / "TranslateDemo_auto.py",
        root_dir / "data" / "kb_raw" / "apidemo" / "TranslateDemo_auto.py",
    ]


def _load_demo_module() -> object | None:
    global _DEMO_MOD, _DEMO_LOAD_ATTEMPTED
    if _DEMO_LOAD_ATTEMPTED:
        return _DEMO_MOD

    _DEMO_LOAD_ATTEMPTED = True
    for path in _candidate_demo_paths():
        if not path.exists():
            continue

        spec = importlib.util.spec_from_file_location("kb_translate_demo", str(path))
        if spec is None or spec.loader is None:
            continue

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
        except Exception:
            continue

        if hasattr(module, "translate_text"):
            _DEMO_MOD = module
            return module

    return None


def translate_text(text: str, from_lang: str, to_lang: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""

    demo = _load_demo_module()
    if demo is None:
        return text

    try:
        translated = getattr(demo, "translate_text")(text, from_lang, to_lang)  # type: ignore[misc]
    except Exception:
        return text

    translated = str(translated or "").strip()
    return translated or text


def translate_kb_zh_to_langs(zh_block: Dict, target_langs: List[str] | None = None) -> Dict[str, Dict]:
    if target_langs is None:
        target_langs = ["en", "ja", "fr", "de"]

    fields = ["definition", "symptoms", "diagnosis", "treatment", "notes"]
    zh_texts = zh_block if isinstance(zh_block, dict) else {}
    result: Dict[str, Dict] = {}

    for lang in target_langs:
        translated = {}
        for field in fields:
            value = zh_texts.get(field, "")
            if isinstance(value, list):
                translated[field] = [
                    translate_text(str(item), "zh", lang) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                translated[field] = translate_text(str(value), "zh", lang) if value else ""
        result[lang] = translated

    return result


def translate_kb_entity(zh_block: Dict, target_langs: List[str] | None = None) -> Dict[str, Dict]:
    langs = translate_kb_zh_to_langs(zh_block, target_langs)
    term = zh_block.get("term", "")
    aliases = zh_block.get("aliases", [])

    for lang, fields in langs.items():
        if term:
            fields["term"] = translate_text(term, "zh", lang)
        if aliases:
            fields["aliases"] = [translate_text(alias, "zh", lang) for alias in (aliases or [])]

    return langs
