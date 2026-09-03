"""
Generate structured medical KB entries using LLM.

Usage:
    python scripts/generate_kb.py                    # Generate all missing entries
    python scripts/generate_kb.py --limit 10         # Generate first 10
    python scripts/generate_kb.py --dry-run          # Show what would be generated
    python scripts/generate_kb.py --category endocrine  # Only one category
"""
import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend" / "apps"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

KB_RAW_DIR = ROOT / "backend" / "data" / "kb_raw"
CATALOG_PATH = KB_RAW_DIR / "disease_catalog.json"
OUTPUT_PATH = ROOT / "backend" / "data" / "kb" / "entities_generated.json"
KB_ENTITIES_PATH = ROOT / "backend" / "data" / "kb" / "entities.json"

GENERATION_PROMPT = """You are a medical knowledge base generator. You must output ONLY valid JSON, no extra text.

Task: Generate structured medical information about the disease "{name_zh}" (English: "{name_en}").

Output this EXACT JSON structure:
{{
  "canonical_key": "{name_en}",
  "category": "disease",
  "lang_terms": {{
    "zh": {{ "name": "{name_zh}", "aliases": ["alias1", "alias2"] }},
    "en": {{ "name": "{name_en}", "aliases": ["alias1", "alias2"] }}
  }},
  "lang_texts": {{
    "zh": {{
      "definition": "简洁的疾病定义（1-2句）",
      "symptoms": "主要症状列表，用中文逗号分隔。3-6项。",
      "causes": "主要病因，用中文逗号分隔。2-4项。",
      "treatment": "主要治疗方式，用中文逗号分隔。3-5项。",
      "prevention": "预防措施，用中文逗号分隔。2-4项。"
    }},
    "en": {{
      "definition": "Concise disease definition (1-2 sentences).",
      "symptoms": "Main symptoms as a list. 3-6 items.",
      "causes": "Main causes. 2-4 items.",
      "treatment": "Main treatments. 3-5 items.",
      "prevention": "Prevention measures. 2-4 items."
    }}
  }}
}}

Rules:
1. All medical content must be accurate and evidence-based.
2. Chinese text should use medical-standard terminology.
3. Each field should be 1-4 sentences maximum.
4. Use ONLY ASCII double quotes for JSON keys and values.
5. Do NOT add markdown code fences or explanations.
6. Output ONLY the JSON object.
"""


def get_llm():
    from backend.core.llm.qa_siliconflow import SiliconFlowQA, reset_qa_generator
    reset_qa_generator()
    model = os.environ.get("KB_GEN_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    api_key = os.environ.get("SILICONFLOW_API_KEY", "")
    return SiliconFlowQA(model=model, api_key=api_key)


def load_existing_keys() -> set:
    """Load canonical_keys already in the KB."""
    existing = set()
    for path in [KB_ENTITIES_PATH, OUTPUT_PATH]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for e in (data if isinstance(data, list) else []):
                ck = (e.get("canonical_key") or "").strip().lower()
                if ck:
                    existing.add(ck)
        except Exception:
            pass
    return existing


def generate_entry(disease: dict, llm, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """Generate a single disease entry via LLM."""
    name_en = disease["en"]
    name_zh = disease["zh"]
    aliases = disease.get("aliases", [])

    prompt = GENERATION_PROMPT.format(name_en=name_en, name_zh=name_zh)

    for attempt in range(max_retries):
        try:
            resp = llm.client.chat.completions.create(
                model=llm.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.2 if attempt == 0 else 0.4,
            )
            raw = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            time.sleep(2)
            continue

        # Extract JSON
        raw = raw.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{[^{}]*"canonical_key"[^{}]*\}', raw, re.DOTALL)
            if not match:
                match = re.search(r'\{.+\}', raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    print(f"  Attempt {attempt+1}: JSON parse failed after regex")
                    continue
            else:
                print(f"  Attempt {attempt+1}: No JSON found in response")
                continue

        # Validate required fields
        lang_texts = data.get("lang_texts", {})
        zh_texts = lang_texts.get("zh", {})
        if not zh_texts.get("definition") or not zh_texts.get("symptoms"):
            print(f"  Attempt {attempt+1}: Missing required zh text fields")
            continue

        # Build final entry
        entry = {
            "entity_id": f"disease_{name_en.replace(' ', '_').replace('-', '_').lower()}",
            "canonical_key": name_en,
            "category": "disease",
            "source": "llm_generated",
            "source_type": "file",
            "lang_terms": {
                "zh": {
                    "name": name_zh,
                    "aliases": aliases
                },
                "en": {
                    "name": name_en,
                    "aliases": []
                }
            },
            "lang_texts": {}
        }

        for lang in ["zh", "en"]:
            if lang in lang_texts:
                entry["lang_texts"][lang] = {
                    "definition": (lang_texts[lang].get("definition") or "").strip(),
                    "symptoms": (lang_texts[lang].get("symptoms") or "").strip(),
                    "causes": (lang_texts[lang].get("causes") or "").strip(),
                    "treatment": (lang_texts[lang].get("treatment") or "").strip(),
                    "prevention": (lang_texts[lang].get("prevention") or "").strip(),
                }

        return entry

    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate medical KB entries via LLM")
    parser.add_argument("--limit", type=int, default=0, help="Max entries to generate")
    parser.add_argument("--category", type=str, default="", help="Only generate from this category")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    parser.add_argument("--model", type=str, default="", help="Override LLM model")
    args = parser.parse_args()

    if args.model:
        os.environ["KB_GEN_MODEL"] = args.model

    if not CATALOG_PATH.exists():
        print(f"Catalog not found: {CATALOG_PATH}")
        return

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    diseases_dict = catalog.get("diseases", {})

    existing_keys = load_existing_keys()
    print(f"Existing KB entries: {len(existing_keys)}")

    # Flatten disease list
    all_diseases = []
    for category, diseases in diseases_dict.items():
        if args.category and args.category != category:
            continue
        for d in diseases:
            key = d["en"].lower()
            if key in existing_keys:
                continue
            all_diseases.append((category, d))

    print(f"Categories: {len(diseases_dict)}, diseases to generate: {len(all_diseases)}")

    if args.dry_run:
        print("\nWould generate:")
        for cat, d in all_diseases[:args.limit or len(all_diseases)]:
            print(f"  [{cat}] {d['zh']} ({d['en']})")
        return

    if not all_diseases:
        print("All diseases already exist in KB.")
        return

    # Load existing generated data
    generated = []
    if OUTPUT_PATH.exists():
        try:
            generated = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            generated = []

    llm = get_llm()
    if not llm.client:
        print("ERROR: API client not available. Check SILICONFLOW_API_KEY.")
        return

    print(f"Using model: {llm.model}")
    count = 0
    for category, disease in all_diseases:
        if args.limit and count >= args.limit:
            break

        name_zh = disease["zh"]
        name_en = disease["en"]
        print(f"\n[{category}] {name_zh} ({name_en}) ...", end=" ", flush=True)

        entry = generate_entry(disease, llm)
        if entry:
            entry["category"] = category
            generated.append(entry)
            # Save after each entry
            OUTPUT_PATH.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")
            print("OK")
            count += 1
        else:
            print("FAILED (skipping)")

        time.sleep(0.5)  # Rate limiting

    print(f"\nGenerated {count} entries. Total: {len(generated)}")
    print(f"Output: {OUTPUT_PATH}")
    print("\nNext: run 'python scripts/build_kb_multilang.py' to rebuild the index.")


if __name__ == "__main__":
    main()
