import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from .models import Feedback


def get_feedback_analytics(scene: str = "qa", days: int = 30) -> Dict[str, Any]:
    """Generate comprehensive feedback analytics for dashboard."""
    since = timezone.now() - timedelta(days=days)

    base_qs = Feedback.objects.filter(scene=scene, created_at__gte=since)

    total = base_qs.count()
    if total == 0:
        return {"error": f"No feedback in last {days} days for scene={scene}", "total": 0}

    positive = base_qs.filter(rating__gte=1).count()
    negative = base_qs.filter(rating__lte=-1).count()
    with_correction = base_qs.filter(
        Q(corrected_answer__gt="") | Q(corrected_translation__gt="")
    ).count()

    dim_stats = {}
    for dim in ["rating_accuracy", "rating_clarity", "rating_completeness", "rating_safety"]:
        agg = base_qs.exclude(**{dim: None}).aggregate(
            avg=Avg(dim), count=Count(dim), low=Count(dim, filter=Q(**{f"{dim}__lte": 2}))
        )
        if agg["count"] and agg["count"] > 0:
            dim_stats[dim] = {
                "avg": round(float(agg["avg"]), 2),
                "count": agg["count"],
                "low_ratio": round(float(agg["low"]) / agg["count"], 3),
            }

    pending = base_qs.filter(resolution="pending").count()
    accepted = base_qs.filter(resolution="accepted").count()
    rejected = base_qs.filter(resolution="rejected").count()

    by_entity: Dict[str, dict] = defaultdict(lambda: {"negative": 0, "total": 0, "corrections": []})
    for fb in base_qs.filter(rating__lte=-1).select_related("user")[:200]:
        for ek in (fb.related_entity_keys or []):
            by_entity[ek]["negative"] += 1
            by_entity[ek]["total"] += 1
            if fb.has_correction():
                by_entity[ek]["corrections"].append({
                    "feedback_id": fb.id,
                    "date": fb.created_at.isoformat(),
                    "comment": fb.comment[:200],
                    "correction": (fb.corrected_answer or fb.corrected_translation or "")[:300],
                })

    for fb in base_qs[:200]:
        for ek in (fb.related_entity_keys or []):
            if ek in by_entity:
                by_entity[ek]["total"] += 1

    top_problematic = sorted(
        [{"entity_key": ek, **v} for ek, v in by_entity.items()],
        key=lambda x: x["negative"], reverse=True
    )[:10]

    recent_corrections = []
    for fb in base_qs.filter(
        Q(corrected_answer__gt="") | Q(corrected_translation__gt="")
    ).order_by("-created_at")[:20]:
        recent_corrections.append({
            "id": fb.id,
            "date": fb.created_at.isoformat(),
            "scene": fb.scene,
            "task_type": fb.task_type,
            "rating": fb.rating,
            "comment": fb.comment[:200],
            "correction": (fb.corrected_answer or fb.corrected_translation or "")[:500],
            "entity_keys": fb.related_entity_keys,
            "resolution": fb.resolution,
        })

    resolution_breakdown = {
        "pending": pending,
        "accepted": accepted,
        "rejected": rejected,
        "total": pending + accepted + rejected,
    }

    rating_distribution = {}
    for r in range(-1, 2):
        rating_distribution[str(r)] = base_qs.filter(rating=r).count()
    rating_distribution["positive"] = positive
    rating_distribution["negative"] = negative
    rating_distribution["correction_rate"] = round(with_correction / max(1, negative), 3)

    return {
        "period_days": days,
        "scene": scene,
        "total": total,
        "positive": positive,
        "negative": negative,
        "positivity_rate": round(positive / max(1, total), 3),
        "negativity_rate": round(negative / max(1, total), 3),
        "with_correction": with_correction,
        "resolution_breakdown": resolution_breakdown,
        "rating_distribution": rating_distribution,
        "dimensional_scores": dim_stats,
        "top_problematic_entities": top_problematic,
        "recent_corrections": recent_corrections,
    }


def export_feedback_for_finetuning(
    scene: str = "qa",
    days: int = 90,
    min_rating: int = 1,
    include_corrections_only: bool = False,
    max_samples: int = 100,
) -> List[Dict[str, Any]]:
    """
    Export high-quality feedback as training data for future fine-tuning.
    
    This is the data flywheel: collect user corrections and positive examples
    to improve the model over time.
    """
    since = timezone.now() - timedelta(days=days)

    qs = Feedback.objects.filter(
        scene=scene, created_at__gte=since, rating__gte=min_rating
    ).select_related("user")

    if include_corrections_only:
        qs = qs.filter(Q(corrected_answer__gt="") | Q(corrected_translation__gt=""))

    samples = []
    for fb in qs.order_by("-created_at")[:max_samples]:
        extra = fb.extra or {}
        question = extra.get("question", "") or extra.get("input_text", "")
        ai_answer = extra.get("ai_answer", "") or extra.get("original_translation", "")
        human_correction = fb.corrected_answer or fb.corrected_translation or ""

        sample = {
            "feedback_id": fb.id,
            "date": fb.created_at.isoformat(),
            "source": "user_feedback",
            "scene": fb.scene,
            "question": question,
            "ai_response": ai_answer,
            "human_correction": human_correction,
            "user_comment": fb.comment,
            "rating": fb.rating,
            "dimensional_ratings": {
                "accuracy": fb.rating_accuracy,
                "clarity": fb.rating_clarity,
                "completeness": fb.rating_completeness,
                "safety": fb.rating_safety,
            },
            "entity_keys": fb.related_entity_keys,
            "label": "positive" if fb.rating >= 1 else "negative",
        }

        if human_correction and question:
            sample["preference_pair"] = {
                "chosen": human_correction,
                "rejected": ai_answer,
            }

        samples.append(sample)

    return samples


def get_weekly_bad_case_report() -> Dict[str, Any]:
    """Generate a weekly report of the worst-performing cases."""
    since = timezone.now() - timedelta(days=7)

    bad_cases = Feedback.objects.filter(
        scene="qa", created_at__gte=since, rating__lte=-1
    ).order_by("-created_at")[:50]

    report = {
        "period": f"{since.isoformat()} to {timezone.now().isoformat()}",
        "total_bad_cases": bad_cases.count(),
        "top_issues": [],
        "cases": [],
    }

    entity_issues: Dict[str, int] = defaultdict(int)
    reason_issues: Dict[str, int] = defaultdict(int)

    for fb in bad_cases:
        for ek in (fb.related_entity_keys or []):
            entity_issues[ek] += 1
        reason = (fb.extra or {}).get("reason", "") or "unspecified"
        reason_issues[reason] += 1

        extra = fb.extra or {}
        report["cases"].append({
            "id": fb.id,
            "date": fb.created_at.isoformat(),
            "comment": fb.comment[:300],
            "correction": (fb.corrected_answer or fb.corrected_translation or "")[:300],
            "entity_keys": fb.related_entity_keys,
            "reason": reason,
            "question": extra.get("question", "") or extra.get("input_text", "")[:200],
            "resolution": fb.resolution,
        })

    report["top_issues"] = sorted(
        [{"entity": ek, "count": c} for ek, c in entity_issues.items()],
        key=lambda x: x["count"], reverse=True
    )[:10]

    report["top_reasons"] = sorted(
        [{"reason": r, "count": c} for r, c in reason_issues.items()],
        key=lambda x: x["count"], reverse=True
    )[:10]

    return report
