from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .term_matcher import extract_terms_for_text
from .views import build_term_cards


MEDICAL_HINTS_ZH = [
    "患者", "病史", "症状", "诊断", "治疗", "用药", "服药", "血压", "血糖", "检查",
    "化验", "检验", "报告", "指标", "住院", "门诊", "复诊", "药物", "剂量", "处方",
]

MEDICAL_HINTS_EN = [
    "patient", "history", "symptom", "diagnosis", "treatment", "medication", "drug",
    "blood pressure", "blood glucose", "examination", "report", "test", "dose",
    "prescription", "clinic", "hospital",
]

MEDICAL_HINTS_FR = [
    "patient", "symptome", "diagnostic", "traitement", "médicament", "rapport",
    "examen", "ordonnance", "hôpital",
]

MEDICAL_HINTS_DE = [
    "patient", "symptom", "diagnose", "behandlung", "medikament", "bericht",
    "untersuchung", "rezept", "krankenhaus",
]

MEDICAL_HINTS_JA = [
    "患者", "症状", "診断", "治療", "薬", "薬剤", "検査", "報告", "処方", "病院",
]


def _count_medical_hints(text: str, lang: str) -> int:
    lowered = text.lower()
    if lang == "zh":
        hints = MEDICAL_HINTS_ZH
    elif lang == "en":
        hints = MEDICAL_HINTS_EN
    elif lang == "fr":
        hints = MEDICAL_HINTS_FR
    elif lang == "de":
        hints = MEDICAL_HINTS_DE
    elif lang == "ja":
        hints = MEDICAL_HINTS_JA
    else:
        hints = MEDICAL_HINTS_ZH
    return sum(1 for hint in hints if hint.lower() in lowered)


def _build_summary(text: str, lang: str, terms: list[dict], is_medical: bool) -> str:
    unique_terms = []
    seen = set()
    for item in terms:
        term = (item.get("term") or "").strip()
        key = term.lower()
        if not term or key in seen:
            continue
        seen.add(key)
        unique_terms.append(term)

    if not unique_terms:
        return "未识别到明显的医学术语。"

    if not is_medical:
        return (
            f"识别到 {len(unique_terms)} 个疑似医学相关术语，但整段文本整体不像标准医疗文本。"
            f" 当前结果更适合作为术语提示，而不是病例摘要。"
        )

    if len(unique_terms) == 1:
        return f"识别到 1 个核心医学术语：{unique_terms[0]}。可结合右侧术语卡片继续查看释义。"

    return f"识别到 {len(unique_terms)} 个医学相关术语，主要包括：{'、'.join(unique_terms[:10])}{'等' if len(unique_terms) > 10 else ''}。"


def _build_enhanced_term_cards(term_cards: list[dict]) -> list[dict]:
    enhanced = []
    for card in term_cards:
        category = (card.get("type") or "term").strip().lower()
        explain_text = (card.get("explain_text") or "").strip()
        aliases = [
            ("中文", (card.get("term_zh") or "").strip()),
            ("英文", (card.get("term_en") or "").strip()),
            ("日文", (card.get("term_ja") or "").strip()),
            ("法文", (card.get("term_fr") or "").strip()),
            ("德文", (card.get("term_de") or "").strip()),
        ]
        aliases = [{"label": label, "value": value} for label, value in aliases if value]

        card["multilang_terms"] = aliases

        if category in {"drug", "medicine", "medication"}:
            card["usage_hint"] = "药品相关术语，建议关注适应症、用法用量与注意事项。"
        elif category in {"disease"}:
            card["usage_hint"] = "疾病相关术语，建议结合症状、诊断与治疗信息理解。"
        elif category in {"symptom"}:
            card["usage_hint"] = "症状相关术语，可继续结合问答模块查看常见原因与处理建议。"
        else:
            card["usage_hint"] = "可结合右侧术语卡片与后续翻译/问答继续理解。"

        if not explain_text and category in {"drug", "medicine", "medication"}:
            card["explain_text"] = "该条目为药品相关术语，当前知识库中暂无详细释义。"

        enhanced.append(card)
    return enhanced


class MedicalTextAnalysisView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        text = (request.data.get("text") or "").strip()
        lang = (request.data.get("lang") or "zh").strip().lower()

        if not text:
            return Response({"detail": "text required"}, status=status.HTTP_400_BAD_REQUEST)

        terms = extract_terms_for_text(text, lang=lang, limit=120)
        hint_count = _count_medical_hints(text, lang)
        unique_term_count = len({(item.get("term") or "").strip().lower() for item in terms if (item.get("term") or "").strip()})
        is_medical = bool(
            unique_term_count >= 2
            or hint_count >= 2
            or (unique_term_count >= 1 and hint_count >= 1)
        )
        term_cards = build_term_cards(terms, lang=lang, top_k_each=4) if terms else []
        term_cards = _build_enhanced_term_cards(term_cards)
        summary = _build_summary(text, lang, terms, is_medical)

        return Response({
            "text": text,
            "lang": lang,
            "summary": summary,
            "is_medical_text": is_medical,
            "medical_hint_count": hint_count,
            "terms": terms,
            "term_cards": term_cards if is_medical else term_cards[: min(len(term_cards), 2)],
        })
