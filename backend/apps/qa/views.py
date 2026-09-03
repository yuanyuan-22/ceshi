import json
import re
import time
from typing import Any, Dict, Optional

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.utils import write_audit
from backend.core.llm.qa_siliconflow import get_qa_generator
from backend.core.rag.kb import get_kb

from .models import QATask


LANG_RESPONSES = {
    "zh": "根据当前知识库，暂时无法可靠回答这个问题。",
    "en": "This information cannot be determined reliably from the current knowledge base.",
    "ja": "現在の知識ベースだけでは、この情報を確実に判断できません。",
    "fr": "Cette information ne peut pas être déterminée de manière fiable à partir de la base de connaissances actuelle.",
    "de": "Diese Information kann aus der aktuellen Wissensbasis nicht zuverlässig bestimmt werden.",
}

SECTION_LABELS = {
    "zh": {
        "definition": "定义",
        "symptoms": "症状",
        "diagnosis": "诊断",
        "treatment": "治疗",
        "notes": "说明",
    },
    "en": {
        "definition": "Definition",
        "symptoms": "Symptoms",
        "diagnosis": "Diagnosis",
        "treatment": "Treatment",
        "notes": "Notes",
    },
}


def _detect_question_lang(text: str) -> str:
    text = (text or "").strip()
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    lowered = text.lower()
    if re.search(r"[àâçéèêëîïôûùüÿœæ]", lowered):
        return "fr"
    if re.search(r"[äöüß]", lowered):
        return "de"
    return "en"


def _expand_short_query(text: str) -> str:
    text = (text or "").strip()
    if re.search(r"[\u4e00-\u9fff]", text) and len(text) <= 6:
        return f"{text}的病因、症状、诊断和治疗"
    if re.fullmatch(r"[A-Za-z\s]+", text) and len(text.split()) <= 2:
        return f"{text} causes, symptoms, diagnosis, and treatment"
    return text


def _preferred_retrieval_langs(question: str, answer_lang: str) -> list[str]:
    detected = _detect_question_lang(question)
    mapping = {
        "zh": ["zh", "en"],
        "en": ["en", "zh"],
        "ja": ["zh", "en", "ja"],
        "fr": ["zh", "en", "fr"],
        "de": ["zh", "en", "de"],
    }
    langs = mapping.get(answer_lang, mapping.get(detected, ["zh", "en"]))
    out = []
    for lang in langs:
        if lang not in out:
            out.append(lang)
    return out


def _choose_draft_lang(question: str, requested_lang: str, hits: Optional[list[Dict[str, Any]]] = None) -> str:
    detected = _detect_question_lang(question)
    if detected == "zh":
        return "zh"
    if detected == "en":
        return "en"

    if hits:
        for lang in ("zh", "en", requested_lang):
            for hit in hits:
                hit_lang = (hit.get("explain_lang") or hit.get("lang") or "").strip()
                if hit_lang == lang:
                    return lang

    if requested_lang in {"fr", "de", "ja"}:
        return "zh"
    return requested_lang or "zh"


def _is_abnormal_answer(answer: str) -> bool:
    text = (answer or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered.startswith("failed to ") or "connection error" in lowered or "service is unavailable" in lowered:
        return True
    if len(text) > 4000:
        return True
    if re.search(r"(.)\1{8,}", text):
        return True
    if re.search(r"([.。,，!?！？;；:\-])(?:\s*\1){8,}", text):
        return True
    if re.search(r"(?:\b[A-Za-z]{1,3}\b[\s,.;:!?-]*){25,}", text):
        return True
    alpha = re.findall(r"[A-Za-z]", text)
    if len(text) >= 120 and alpha:
        top_count = max(text.count(ch) for ch in set(alpha))
        if top_count / max(1, len(alpha)) > 0.45:
            return True
    return False


def _looks_like_wrong_language(answer: str, lang: str) -> bool:
    text = (answer or "").strip()
    if not text:
        return True
    if lang == "zh":
        return not bool(re.search(r"[\u4e00-\u9fff]", text))
    if lang == "ja":
        return not bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text))
    if lang == "fr":
        return bool(re.search(r"[\u4e00-\u9fff]", text))
    if lang == "de":
        return bool(re.search(r"[\u4e00-\u9fff]", text))
    if lang == "en":
        return bool(re.search(r"[\u4e00-\u9fff]", text))
    return False


def _parse_structured_sections(text: str) -> Dict[str, str]:
    text = (text or "").strip()
    if not text:
        return {}

    patterns = [
        ("definition", r"(?:定义|definition)\s*[:：]\s*(.+)"),
        ("symptoms", r"(?:症状|symptoms)\s*[:：]\s*(.+)"),
        ("diagnosis", r"(?:诊断|diagnosis)\s*[:：]\s*(.+)"),
        ("treatment", r"(?:治疗|treatment)\s*[:：]\s*(.+)"),
        ("notes", r"(?:说明|notes)\s*[:：]\s*(.+)"),
    ]

    out: Dict[str, str] = {}
    for key, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            out[key] = match.group(1).strip()
    return out


def _build_extractive_answer(hit: Dict[str, Any], lang: str) -> str:
    text = (hit.get("explain_text") or hit.get("text") or "").strip()
    if not text:
        return ""

    sections = _parse_structured_sections(text)
    labels = SECTION_LABELS.get(lang, SECTION_LABELS["zh"])

    if lang == "zh":
        parts = []
        if sections.get("definition"):
            parts.append(f"{hit.get('title') or '该疾病'}{labels['definition']}：{sections['definition']}")
        if sections.get("symptoms"):
            parts.append(f"{labels['symptoms']}：{sections['symptoms']}")
        if sections.get("treatment"):
            parts.append(f"{labels['treatment']}：{sections['treatment']}")
        if sections.get("notes"):
            parts.append(f"{labels['notes']}：{sections['notes']}")
        return "\n".join(parts[:4]).strip()

    if lang == "en":
        parts = []
        if sections.get("definition"):
            parts.append(f"{labels['definition']}: {sections['definition']}")
        if sections.get("symptoms"):
            parts.append(f"{labels['symptoms']}: {sections['symptoms']}")
        if sections.get("treatment"):
            parts.append(f"{labels['treatment']}: {sections['treatment']}")
        if sections.get("notes"):
            parts.append(f"{labels['notes']}: {sections['notes']}")
        return "\n".join(parts[:4]).strip()

    return _build_extractive_answer(hit, "zh")


def _translate_text(text: str, src_lang: str, tgt_lang: str) -> str:
    if not text or src_lang == tgt_lang:
        return text
    generator = get_qa_generator()
    return generator.translate(text=text, src_lang=src_lang, tgt_lang=tgt_lang, max_tokens=500, temperature=0.1)


def _translate_extractive_answer(hit: Dict[str, Any], requested_lang: str) -> str:
    base_text = _build_extractive_answer(hit, "zh")
    if not base_text:
        return ""
    if requested_lang == "zh":
        return base_text
    translated = _translate_text(base_text, src_lang="zh", tgt_lang=requested_lang)
    translated = (translated or "").strip()
    if translated and not _is_abnormal_answer(translated) and not _looks_like_wrong_language(translated, requested_lang):
        return translated
    return ""


def _finalize_answer(
    draft_answer: str,
    draft_lang: str,
    requested_lang: str,
    hits: Optional[list[Dict[str, Any]]] = None,
) -> str:
    fallback = LANG_RESPONSES.get(requested_lang, LANG_RESPONSES["zh"])
    text = (draft_answer or "").strip()

    if text and not _is_abnormal_answer(text) and not _looks_like_wrong_language(text, draft_lang):
        if requested_lang == draft_lang:
            return text
        translated = _translate_text(text, src_lang=draft_lang, tgt_lang=requested_lang)
        translated = (translated or "").strip()
        if translated and not _is_abnormal_answer(translated) and not _looks_like_wrong_language(translated, requested_lang):
            return translated

    if hits:
        extractive = _translate_extractive_answer(hits[0], requested_lang)
        if extractive:
            return extractive

    return fallback


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ask_rag_view(request):
    data = request.data or {}
    question = (data.get("question") or "").strip()
    requested_lang = (data.get("lang") or "zh").lower().strip()
    top_k = int(data.get("top_k") or 5)

    if not question:
        return Response({"error": "question is required"}, status=400)

    try:
        kb = get_kb()
        search_query = _expand_short_query(question)
        hits = kb.search(
            search_query,
            top_k=top_k,
            preferred_langs=_preferred_retrieval_langs(question, requested_lang),
        )
        draft_lang = _choose_draft_lang(question, requested_lang, hits)
        return Response({
            "question": question,
            "requested_lang": requested_lang,
            "draft_lang": draft_lang,
            "hits": hits,
            "total_retrieved": len(hits),
            "top_k_requested": top_k,
            "mode": "retrieval_debug",
        })
    except Exception as e:
        return Response({"error": str(e)}, status=500)


class QAView(APIView):
    def post(self, request):
        t0 = time.time()

        def _audit(action: str, status_code: int, extra: Optional[Dict[str, Any]] = None):
            latency_ms_ = int((time.time() - t0) * 1000)
            write_audit(
                request=request,
                action=action,
                status_code=status_code,
                latency_ms=latency_ms_,
                extra=extra or {},
            )

        question = (request.data.get("question") or "").strip()
        requested_lang = (request.data.get("lang") or "zh").lower().strip()
        fast_mode = request.data.get("fast_mode", False)

        try:
            top_k = int(request.data.get("top_k", 8))
        except Exception:
            top_k = 8

        if not question:
            return Response({"error": "question required"}, status=400)

        requested_lang = requested_lang or "zh"
        top_k = max(1, min(top_k, 15))
        context = ""

        if len(question) < 2:
            llm_answer = LANG_RESPONSES.get(requested_lang, LANG_RESPONSES["zh"])
            sources = []
            confidence = 0.0
            hits = []
            draft_lang = requested_lang
        else:
            kb = get_kb()
            search_query = _expand_short_query(question)
            hits = kb.search(
                search_query,
                top_k=top_k,
                preferred_langs=_preferred_retrieval_langs(question, requested_lang),
            )
            draft_lang = _choose_draft_lang(question, requested_lang, hits)

            sources = []
            context_list = []

            for h in hits:
                explain = (h.get("explain_text") or "").strip()
                text = explain if explain else (h.get("text") or "")
                if not text:
                    continue

                snippet = text[:300]
                context_list.append(text)
                sources.append({
                    "title": h.get("title", ""),
                    "snippet": snippet,
                    "score": round(float(h.get("score", 0)), 4),
                    "term_en": h.get("term_en", ""),
                    "term_zh": h.get("term_zh", ""),
                    "source": h.get("source", ""),
                })

            context = "\n\n".join(context_list[:3])

            if not context.strip():
                llm_answer = LANG_RESPONSES.get(requested_lang, LANG_RESPONSES["zh"])
            else:
                generator = get_qa_generator()
                try:
                    draft_answer = generator.generate(
                        prompt="",
                        context=context,
                        question=question,
                        lang=draft_lang,
                        max_tokens=500,
                        temperature=0.3,
                    )
                except Exception:
                    draft_answer = ""

                llm_answer = _finalize_answer(
                    draft_answer=draft_answer,
                    draft_lang=draft_lang,
                    requested_lang=requested_lang,
                    hits=hits,
                )

            if sources:
                top_score = float(sources[0]["score"])
                confidence = min(1.0, (top_score + 1) / 2)
            else:
                confidence = 0.2

        history = request.session.get("qa_history", [])
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": llm_answer})
        request.session["qa_history"] = history[-10:]

        latency_ms = int((time.time() - t0) * 1000)
        user = request.user if request.user.is_authenticated else None

        auto_accuracy = None
        auto_completeness = None
        auto_relevance = None
        auto_judge_raw = {}
        if request.data.get("auto_score", False) and llm_answer and context.strip():
            try:
                from evaluation.services import judge_answer_quality
                judge_result = judge_answer_quality(question, llm_answer, context)
                if "error" not in judge_result:
                    auto_accuracy = judge_result.get("accuracy")
                    auto_completeness = judge_result.get("completeness")
                    auto_relevance = judge_result.get("relevance")
                    auto_judge_raw = judge_result
            except Exception:
                pass

        task = QATask.objects.create(
            user=user,
            question=question,
            lang=requested_lang,
            answer=llm_answer,
            confidence=confidence,
            sources_json=sources,
            auto_accuracy=auto_accuracy,
            auto_completeness=auto_completeness,
            auto_relevance=auto_relevance,
            auto_judge_raw=auto_judge_raw,
            latency_ms=latency_ms,
            status="SUCCESS",
        )

        _audit(
            "qa.ask",
            200,
            {
                "task_id": task.id,
                "fast_mode": fast_mode,
                "requested_lang": requested_lang,
                "draft_lang": draft_lang,
            },
        )

        return Response({
            "task_id": task.id,
            "answer": llm_answer,
            "confidence": confidence,
            "sources": sources,
            "total_retrieved": len(sources),
            "top_k_requested": top_k,
            "latency_ms": latency_ms,
            "mode": "rag_siliconflow",
            "model": get_qa_generator().model,
            "fast_mode": fast_mode,
            "lang": requested_lang,
            "requested_lang": requested_lang,
            "draft_lang": draft_lang,
            "auto_score": {
                "accuracy": auto_accuracy,
                "completeness": auto_completeness,
                "relevance": auto_relevance,
            } if auto_accuracy is not None else None,
        })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def qa_stream_view(request):
    """Streaming QA endpoint using Server-Sent Events."""
    question = (request.data.get("question") or "").strip()
    requested_lang = (request.data.get("lang") or "zh").lower().strip()
    top_k = min(int(request.data.get("top_k", 8)), 10)

    if not question:
        return Response({"error": "question required"}, status=400)

    kb = get_kb()
    search_query = _expand_short_query(question)
    hits = kb.search(search_query, top_k=top_k, preferred_langs=_preferred_retrieval_langs(question, requested_lang))
    draft_lang = _choose_draft_lang(question, requested_lang, hits)

    context_list = []
    sources = []
    for h in hits:
        text = (h.get("explain_text") or h.get("text") or "").strip()
        if not text:
            continue
        context_list.append(text)
        sources.append({
            "title": h.get("title", ""),
            "snippet": text[:200],
            "score": round(float(h.get("score", h.get("best_score", 0))), 4),
            "term_zh": h.get("term_zh", ""),
            "term_en": h.get("term_en", ""),
            "source": h.get("source", ""),
        })

    context = "\n\n".join(context_list[:3])

    def event_stream():
        full_answer = ""
        try:
            if not context.strip():
                fallback = LANG_RESPONSES.get(requested_lang, LANG_RESPONSES["zh"])
                full_answer = fallback
                yield f"data: {json.dumps({'token': fallback, 'done': True})}\n\n"
            else:
                generator = get_qa_generator()
                stream = generator.generate_stream(
                    prompt="", context=context, question=question,
                    lang=draft_lang, max_tokens=500, temperature=0.3,
                )
                for chunk in stream:
                    full_answer += chunk
                    yield f"data: {json.dumps({'token': chunk})}\n\n"
        except Exception as e:
            fallback = LANG_RESPONSES.get(requested_lang, LANG_RESPONSES["zh"])
            full_answer = fallback
            yield f"data: {json.dumps({'token': fallback, 'error': str(e)})}\n\n"
        finally:
            top_score = float(sources[0]["score"]) if sources else 0
            confidence = min(1.0, (top_score + 1) / 2)
            yield f"data: {json.dumps({'done': True, 'confidence': confidence, 'sources': sources, 'draft_lang': draft_lang})}\n\n"

            user = request.user if request.user.is_authenticated else None
            QATask.objects.create(
                user=user, question=question, lang=requested_lang,
                answer=full_answer, confidence=confidence,
                sources_json=sources, latency_ms=0, status="SUCCESS",
            )

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class AgentView(APIView):
    """医疗智能体端点：在 RAG 之上支持多步工具调用（查知识库 + 查医生/号源 + 挂号）。

    请求体：{"message": "帮我挂个内科的号", "lang": "zh"}
    返回体：{"answer", "tool_trace"(每一步调了什么工具/参数/结果), "iterations", ...}
    tool_trace 让"模型到底做了什么"完全可见，便于演示与排查。
    """

    def post(self, request):
        t0 = time.time()
        message = (request.data.get("message") or request.data.get("question") or "").strip()
        requested_lang = (request.data.get("lang") or "zh").lower().strip() or "zh"

        if not message:
            return Response({"error": "message required"}, status=400)

        from backend.core.llm.agent import MedicalAgent

        agent = MedicalAgent(user=request.user)
        result = agent.run(message, lang=requested_lang)

        latency_ms = int((time.time() - t0) * 1000)
        write_audit(
            request=request,
            action="qa.agent",
            status_code=200,
            latency_ms=latency_ms,
            extra={
                "iterations": result.get("iterations"),
                "tools": [t.get("tool") for t in result.get("trace", [])],
                "requested_lang": requested_lang,
            },
        )

        return Response({
            "answer": result.get("answer", ""),
            "tool_trace": result.get("trace", []),
            "iterations": result.get("iterations", 0),
            "lang": requested_lang,
            "mode": "agent",
            "model": agent.model,
            "latency_ms": latency_ms,
        })
