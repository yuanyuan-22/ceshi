import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Avg, Count, Q, StdDev
from django.utils import timezone

from .models import AuditLog


# ============================================================
# SLO Definitions
# ============================================================

SLO_TARGETS = {
    "qa.ask": {
        "p50_latency_ms": 3000,
        "p99_latency_ms": 15000,
        "min_confidence": 0.5,
        "success_rate": 0.95,
        "name": "QA Ask Endpoint",
    },
    "translation.translate": {
        "p50_latency_ms": 5000,
        "p99_latency_ms": 30000,
        "min_confidence": 0.6,
        "success_rate": 0.95,
        "name": "Translation Endpoint",
    },
    "qa.ask_stream": {
        "p50_latency_ms": 2000,
        "p99_latency_ms": 10000,
        "min_confidence": 0.5,
        "success_rate": 0.95,
        "name": "QA Streaming Endpoint",
    },
}

ALERT_THRESHOLDS = {
    "latency_spike": {
        "description": "P99 latency exceeds 2x SLO target",
        "severity": "warning",
        "multiplier": 2.0,
    },
    "latency_critical": {
        "description": "P99 latency exceeds 5x SLO target",
        "severity": "critical",
        "multiplier": 5.0,
    },
    "confidence_drop": {
        "description": "Average confidence drops below SLO minimum",
        "severity": "warning",
    },
    "error_rate_high": {
        "description": "Error rate exceeds 1 - SLO success rate",
        "severity": "warning",
    },
    "error_rate_critical": {
        "description": "Error rate > 20%",
        "severity": "critical",
    },
}


# ============================================================
# Health check
# ============================================================

def _compute_percentiles(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"p50": 0, "p95": 0, "p99": 0}
    s = sorted(values)
    n = len(s)
    return {
        "p50": s[n // 2],
        "p95": s[min(int(n * 0.95), n - 1)],
        "p99": s[min(int(n * 0.99), n - 1)],
    }


def get_health_report(window_minutes: int = 60) -> Dict[str, Any]:
    """Real-time health check against SLO targets."""
    since = timezone.now() - timedelta(minutes=window_minutes)

    report: Dict[str, Any] = {
        "timestamp": timezone.now().isoformat(),
        "window_minutes": window_minutes,
        "status": "healthy",
        "alerts": [],
        "endpoints": {},
    }

    for action, slo in SLO_TARGETS.items():
        logs = AuditLog.objects.filter(action=action, created_at__gte=since)
        total = logs.count()
        if total == 0:
            report["endpoints"][action] = {"status": "no_data", "name": slo["name"], "total": 0}
            continue

        success = logs.filter(status_code__lt=400).count()
        fail = total - success
        success_rate = success / max(1, total)

        latencies = list(logs.filter(latency_ms__isnull=False, latency_ms__gt=0)
                         .values_list("latency_ms", flat=True))
        lat_pct = _compute_percentiles(latencies)

        endpoint_status = {
            "name": slo["name"],
            "total": total,
            "success": success,
            "fail": fail,
            "success_rate": round(success_rate, 4),
            "latency": lat_pct,
        }

        alerts = []

        if lat_pct["p99"] > slo["p99_latency_ms"] * ALERT_THRESHOLDS["latency_critical"]["multiplier"]:
            alerts.append({
                "type": "latency_critical",
                "severity": "critical",
                "message": f"{slo['name']}: P99 latency {lat_pct['p99']:.0f}ms exceeds {slo['p99_latency_ms'] * 5}ms critical threshold",
                "value": round(lat_pct["p99"]),
                "threshold": slo["p99_latency_ms"] * 5,
            })
        elif lat_pct["p99"] > slo["p99_latency_ms"] * ALERT_THRESHOLDS["latency_spike"]["multiplier"]:
            alerts.append({
                "type": "latency_spike",
                "severity": "warning",
                "message": f"{slo['name']}: P99 latency {lat_pct['p99']:.0f}ms exceeds {slo['p99_latency_ms'] * 2}ms warning threshold",
                "value": round(lat_pct["p99"]),
                "threshold": slo["p99_latency_ms"] * 2,
            })

        if success_rate < slo["success_rate"]:
            alerts.append({
                "type": "error_rate_high",
                "severity": "warning",
                "message": f"{slo['name']}: Success rate {success_rate:.1%} below {slo['success_rate']:.0%} SLO target",
                "value": round(success_rate, 3),
                "threshold": slo["success_rate"],
            })

        if success_rate < 0.80:
            alerts.append({
                "type": "error_rate_critical",
                "severity": "critical",
                "message": f"{slo['name']}: Success rate {success_rate:.1%} below 80% critical threshold",
                "value": round(success_rate, 3),
                "threshold": 0.80,
            })

        endpoint_status["alerts"] = alerts
        endpoint_status["status"] = "critical" if any(a["severity"] == "critical" for a in alerts) else (
            "degraded" if alerts else "healthy"
        )

        report["endpoints"][action] = endpoint_status
        report["alerts"].extend(alerts)

    if any(a["severity"] == "critical" for a in report["alerts"]):
        report["status"] = "critical"
    elif report["alerts"]:
        report["status"] = "degraded"

    return report


def get_latency_trends(days: int = 7, bucket_minutes: int = 60) -> Dict[str, Any]:
    """Generate latency trend data for dashboard charts."""
    since = timezone.now() - timedelta(days=days)

    trends: Dict[str, list] = {}
    for action in SLO_TARGETS:
        logs = AuditLog.objects.filter(
            action=action, created_at__gte=since, latency_ms__isnull=False, latency_ms__gt=0
        ).order_by("created_at")

        if not logs.exists():
            trends[action] = []
            continue

        bucket_data = defaultdict(list)
        for log in logs:
            ts = log.created_at.replace(second=0, microsecond=0)
            bucket_data[ts].append(log.latency_ms)

        trends[action] = [
            {
                "time": ts.isoformat(),
                "p50": _compute_percentiles(vals)["p50"],
                "p99": _compute_percentiles(vals)["p99"],
                "avg": round(sum(vals) / len(vals), 1),
                "count": len(vals),
            }
            for ts, vals in sorted(bucket_data.items())
        ]

    return {
        "period_days": days,
        "bucket_minutes": bucket_minutes,
        "trends": trends,
        "slo_targets": {
            action: {"p50_ms": slo["p50_latency_ms"], "p99_ms": slo["p99_latency_ms"]}
            for action, slo in SLO_TARGETS.items()
        },
    }


def get_error_patterns(days: int = 7) -> Dict[str, Any]:
    """Identify patterns in error logs for proactive issue detection."""
    since = timezone.now() - timedelta(days=days)
    error_logs = AuditLog.objects.filter(
        created_at__gte=since, status_code__gte=400
    ).order_by("-created_at")[:500]

    if error_logs.count() == 0:
        return {"period_days": days, "total_errors": 0, "patterns": []}

    patterns = []
    by_action: Dict[str, list] = defaultdict(list)
    by_status: Dict[int, list] = defaultdict(list)
    by_path: Dict[str, list] = defaultdict(list)

    for log in error_logs:
        if log.action:
            by_action[log.action].append(log)
        if log.status_code:
            by_status[log.status_code].append(log)
        if log.path:
            by_path[log.path].append(log)

    for action, logs in sorted(by_action.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        patterns.append({
            "type": "action",
            "key": action,
            "count": len(logs),
            "latest": logs[0].created_at.isoformat(),
            "sample_status_codes": list(set(l.status_code for l in logs[:10])),
        })

    for status_code, logs in sorted(by_status.items(), key=lambda x: len(x[1]), reverse=True)[:5]:
        patterns.append({
            "type": "status_code",
            "key": str(status_code),
            "count": len(logs),
            "latest": logs[0].created_at.isoformat(),
        })

    hourly_distribution = defaultdict(int)
    for log in error_logs:
        hour = log.created_at.hour
        hourly_distribution[hour] += 1

    return {
        "period_days": days,
        "total_errors": error_logs.count(),
        "patterns": patterns,
        "hourly_distribution": dict(sorted(hourly_distribution.items())),
    }
