import time
from typing import List, Dict, Any, Optional

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import TranslationTask
from backend.core.llm.translator_hf import translate, translate_with_lora, LANG_CODE_MAP
from audit.utils import write_audit

from .term_matcher import extract_terms_for_text, get_entity_payload

try:
    from backend.core.rag.kb import get_kb
except Exception:
    get_kb = None


def build_term_cards(
    terms: List[Dict[str, Any]],
    lang: str = "zh",
    top_k_each: int = 4,
) -> List[Dict[str, Any]]:
    if get_kb is None:
        kb = None
    else:
        try:
            kb = get_kb()
        except Exception:
            kb = None

    cards = []
    seen = set()

    for t in terms:
        canonical_key = (t.get("canonical_key") or t.get("concept_key") or "").strip()
        matched_term = (t.get("term") or "").strip()

        if canonical_key:
            dedupe_key = canonical_key.lower()
        else:
            dedupe_key = matched_term.lower()

        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        term_zh = (t.get("term_zh") or t.get("zh") or "").strip()
        term_en = (t.get("term_en_full") or t.get("term_en") or "").strip()
        term_fr = (t.get("term_fr") or "").strip()
        term_de = (t.get("term_de") or "").strip()
        term_ja = (t.get("term_ja") or "").strip()

        type_ = (t.get("type") or "term").strip()
        head_source = "kb"

        query_candidates = [
            canonical_key,
            matched_term,
            term_zh,
            term_en,
            term_ja,
            term_fr,
            term_de,
        ]
        query_candidates = [q.strip() for q in query_candidates if q.strip()]
        if not query_candidates:
            continue

        explain_text = ""
        explain_source = ""
        explain_source_type = ""
        entity_payload = get_entity_payload(canonical_key) if canonical_key else {}
        if entity_payload:
            lang_texts = entity_payload.get("lang_texts") or {}
            lang_block = (lang_texts.get(lang) or {})
            for field in ("definition", "notes", "symptoms", "diagnosis", "treatment"):
                value = (lang_block.get(field) or "").strip()
                if value:
                    explain_text = value
                    explain_source = (entity_payload.get("source") or "").strip()
                    explain_source_type = (entity_payload.get("source_type") or "db").strip()
                    break

        def _update_terms_from_hit(h, cur_zh, cur_en, cur_fr, cur_de, cur_ja):
            return (
                cur_zh or (h.get("term_zh") or "").strip(),
                cur_en or (h.get("term_en") or "").strip(),
                cur_fr or (h.get("term_fr") or "").strip(),
                cur_de or (h.get("term_de") or "").strip(),
                cur_ja or (h.get("term_ja") or "").strip(),
            )

        def _is_valid_explain(et, hit_lang):
            if not et or len(et) < 20:
                return False
            return True

        def _lang_match(hit_lang, target_lang):
            return hit_lang == target_lang

        try:
            best_hit = None
            best_score = 0

            if not explain_text and kb is not None:
                for query in query_candidates:
                    hits = kb.search(query, top_k=top_k_each)
                    for h in hits:
                        et = (h.get("explain_text") or "").strip()
                        if not et or len(et) < 20:
                            continue
                        score = 1.0
                        if _lang_match(h.get("lang", ""), lang):
                            score += 2.0
                        if score > best_score:
                            best_score = score
                            best_hit = h
                            if score >= 3.0:
                                break
                    if best_score >= 3.0:
                        break

            if best_hit:
                explain_text = (best_hit.get("explain_text") or "").strip()
                explain_source = (best_hit.get("explain_source") or "").strip()
                explain_source_type = (best_hit.get("explain_source_type") or "").strip()
                term_zh, term_en, term_fr, term_de, term_ja = _update_terms_from_hit(
                    best_hit, term_zh, term_en, term_fr, term_de, term_ja
                )

            if not explain_text and kb is not None:
                for query in query_candidates:
                    hits = kb.search(query, top_k=top_k_each)
                    for h in hits:
                        et = (h.get("text") or "").strip()
                        if et and len(et) > 30:
                            explain_text = et
                            explain_source = (h.get("source") or "").strip()
                            explain_source_type = (h.get("source_type") or "").strip()
                            term_zh, term_en, term_fr, term_de, term_ja = _update_terms_from_hit(
                                h, term_zh, term_en, term_fr, term_de, term_ja
                            )
                            break
                    if explain_text:
                        break

                if not explain_text:
                    for query in query_candidates:
                        hits = kb.search(query, top_k=top_k_each * 3)
                        for h in hits:
                            et = (h.get("text") or "").strip()
                            if et and len(et) > 30:
                                explain_text = et
                                explain_source = (h.get("source") or "").strip()
                                explain_source_type = (h.get("source_type") or "").strip()
                                term_zh, term_en, term_fr, term_de, term_ja = _update_terms_from_hit(
                                    h, term_zh, term_en, term_fr, term_de, term_ja
                                )
                                break
                        if explain_text:
                            break

        except Exception:
            explain_text, explain_source, explain_source_type = "", "", ""

        cards.append({
            "canonical_key": canonical_key,
            "matched_lang": lang,
            "matched_term": matched_term,

            "term_zh": term_zh,
            "term_en": term_en,
            "term_fr": term_fr,
            "term_de": term_de,
            "term_ja": term_ja,

            "type": type_,
            "head_source": head_source,

            "explain_text": explain_text,
            "explain_source": explain_source,
            "explain_source_type": explain_source_type,
        })

    return cards


class TranslateView(APIView):
    def post(self, request):
        t0 = time.time()

        def _audit(action: str, status_code: int, extra: Optional[Dict[str, Any]] = None):
            latency_ms_ = None
            try:
                latency_ms_ = int((time.time() - t0) * 1000)
            except Exception:
                pass
            write_audit(
                request=request,
                action=action,
                status_code=status_code,
                latency_ms=latency_ms_,
                extra=extra or {},
            )

        text = (request.data.get("text") or "").strip()
        src_lang = (request.data.get("src_lang", "en") or "en").lower().strip()
        tgt_lang = (request.data.get("tgt_lang", "zh") or "zh").lower().strip()
        domain = request.data.get("domain", "general")

        if not text:
            _audit("translation.translate", 400, {"error": "text required"})
            return Response({"error": "text required"}, status=status.HTTP_400_BAD_REQUEST)

        supported_langs = sorted(LANG_CODE_MAP.keys())

        if src_lang not in LANG_CODE_MAP or tgt_lang not in LANG_CODE_MAP:
            _audit("translation.translate", 400, {
                "error": "unsupported_language",
                "src_lang": src_lang,
                "tgt_lang": tgt_lang,
                "domain": domain,
                "supported_langs": supported_langs,
            })
            return Response(
                {
                    "error": f"unsupported_language: {src_lang}->{tgt_lang}",
                    "supported_langs": supported_langs,
                    "domain": domain,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            base_translation, lora_translation = translate_with_lora(text=text, src_lang=src_lang, tgt_lang=tgt_lang)
        except Exception as e:
            _audit("translation.translate", 500, {
                "error": "translation_failed",
                "src_lang": src_lang,
                "tgt_lang": tgt_lang,
                "domain": domain,
                "detail": str(e),
            })
            return Response(
                {
                    "error": "translation_failed",
                    "detail": str(e),
                    "src_lang": src_lang,
                    "tgt_lang": tgt_lang,
                    "domain": domain,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        translation = lora_translation

        terms_src = extract_terms_for_text(text, lang=src_lang, limit=80)

        terms_tgt = extract_terms_for_text(translation, lang=tgt_lang, limit=80)

        term_cards = build_term_cards(terms_tgt, lang=tgt_lang, top_k_each=4)
        if not term_cards and terms_src:
            term_cards = build_term_cards(terms_src, lang=src_lang, top_k_each=4)

        latency_ms = int((time.time() - t0) * 1000)
        user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None

        terms_json = {
            "terms_src": terms_src,
            "terms_tgt": terms_tgt,
        }

        task = TranslationTask.objects.create(
            user=user,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            domain=domain,
            input_text=text,
            base_translation=base_translation,
            lora_translation=lora_translation,
            output_text=translation,
            terms_json=terms_json,
            latency_ms=latency_ms,
            status="SUCCESS",
        )

        _audit("translation.translate", 200, {
            "task_id": task.id,
            "src_lang": src_lang,
            "tgt_lang": tgt_lang,
            "domain": domain,
            "terms_src_cnt": len(terms_src),
            "terms_tgt_cnt": len(terms_tgt),
            "term_cards_cnt": len(term_cards),
        })

        return Response({
            "task_id": task.id,
            "source_text": text,
            "translation": translation,
            "base_translation": base_translation,
            "lora_translation": lora_translation,
            "term_cards": term_cards,
            "terms_src": terms_src,
            "terms_tgt": terms_tgt,
            "latency_ms": latency_ms,
        })
