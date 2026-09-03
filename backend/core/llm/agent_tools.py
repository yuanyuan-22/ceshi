# backend/core/llm/agent_tools.py
"""医疗智能体可调用的工具集（Function Calling / Tool Use）。

设计目标：把原本"只会检索 + 回答"的被动 RAG，升级为能真正"做事"的 Agent。
每个工具都是一个真实的业务能力：查知识库、查医生、查号源、挂号、查我的预约。
所有工具都以当前登录用户（self.user）为权限边界，避免越权操作。

对外暴露：
    TOOLS_SPEC         -> 传给大模型的 OpenAI tools schema 列表
    ToolExecutor(user) -> .dispatch(name, args) 执行工具并返回可序列化的 dict
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from django.utils import timezone
from django.utils.dateparse import parse_datetime


# 传给大模型的工具描述。描述写得越清楚，模型越知道该在什么时候调用它。
TOOLS_SPEC: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_medical_knowledge",
            "description": "在医疗知识库中检索疾病、症状、用药等专业信息。当用户询问医学知识、病情解释、治疗建议时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题，使用与用户相同的语言"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 3", "default": 3},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_doctors",
            "description": "查询平台上可预约的医生列表。当用户想挂号、想知道有哪些医生或某科室有谁出诊时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "按科室名筛选，可选，如 内科 / 儿科"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_doctor_available_slots",
            "description": "查询某位医生在指定日期的可预约号源（时间段）。挂号前先用它确认有哪些空闲时段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_id": {"type": "integer", "description": "医生的用户 ID，来自 list_doctors 的结果"},
                    "date": {"type": "string", "description": "日期，格式 YYYY-MM-DD"},
                },
                "required": ["doctor_id", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "为当前登录用户预约挂号。必须先用 get_doctor_available_slots 拿到可用时段，再用其中的 appointment_time 调用本工具，不能编造时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_id": {"type": "integer", "description": "医生的用户 ID"},
                    "appointment_time": {"type": "string", "description": "预约时间，须来自可用号源，ISO 格式如 2026-08-22T09:00:00"},
                    "reason": {"type": "string", "description": "就诊事由，可选"},
                },
                "required": ["doctor_id", "appointment_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_appointments",
            "description": "查询当前登录用户已有的预约记录。当用户问『我的预约』『我挂了哪些号』时使用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class ToolExecutor:
    """按当前用户权限执行工具。dispatch 返回的 dict 会被序列化后回填给大模型。"""

    def __init__(self, user):
        self.user = user

    def dispatch(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"unknown tool: {name}"}
        try:
            return handler(**(arguments or {}))
        except TypeError as e:
            return {"error": f"参数错误: {e}"}
        except Exception as e:  # 工具内部异常不应中断整个 Agent 循环
            return {"error": f"工具执行失败: {e}"}

    # ---- 具体工具实现 ----

    def _tool_search_medical_knowledge(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        from backend.core.rag.kb import get_kb

        top_k = max(1, min(int(top_k or 3), 6))
        hits = get_kb().search(query, top_k=top_k)
        results = []
        for h in hits:
            text = (h.get("explain_text") or h.get("text") or "").strip()
            if not text:
                continue
            results.append({
                "title": h.get("title", ""),
                "snippet": text[:300],
                "score": round(float(h.get("best_score", h.get("score", 0.0))), 4),
                "source": h.get("source", ""),
            })
        return {"query": query, "results": results, "count": len(results)}

    def _tool_list_doctors(self, department: str = "") -> Dict[str, Any]:
        from backend.apps.appointments.models import DoctorProfile

        qs = DoctorProfile.objects.select_related("user").filter(is_active=True)
        if department:
            qs = qs.filter(department__icontains=department)
        doctors = [{
            "doctor_id": p.user_id,
            "name": p.user.get_full_name() or p.user.username,
            "department": p.department,
            "hospital": p.hospital,
            "title": p.title,
        } for p in qs.order_by("department", "user__username")]
        return {"doctors": doctors, "count": len(doctors)}

    def _tool_get_doctor_available_slots(self, doctor_id: int, date: str) -> Dict[str, Any]:
        from backend.apps.appointments.models import Appointment, DoctorSchedule

        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return {"error": "日期格式应为 YYYY-MM-DD"}

        schedules = DoctorSchedule.objects.filter(
            doctor_id=doctor_id, schedule_date=target_date, is_active=True,
        ).order_by("start_time")

        slots = []
        seen = set()
        for sch in schedules:
            cur = datetime.combine(target_date, sch.start_time)
            end = datetime.combine(target_date, sch.end_time)
            tz = timezone.get_current_timezone()
            while cur < end:
                key = cur.isoformat()
                if key not in seen:
                    used = Appointment.objects.filter(
                        doctor_id=doctor_id,
                        appointment_time=timezone.make_aware(cur, tz),
                    ).exclude(status=Appointment.STATUS_CANCELLED).count()
                    if used < sch.max_appointments_per_slot:
                        seen.add(key)
                        slots.append({
                            "appointment_time": key,
                            "remaining": sch.max_appointments_per_slot - used,
                        })
                cur += timedelta(minutes=sch.slot_minutes)
        return {"doctor_id": doctor_id, "date": target_date.isoformat(), "slots": slots, "count": len(slots)}

    def _tool_book_appointment(self, doctor_id: int, appointment_time: str, reason: str = "") -> Dict[str, Any]:
        from backend.apps.appointments.models import Appointment
        from backend.apps.appointments.serializers import AppointmentCreateSerializer

        if not (self.user and self.user.is_authenticated):
            return {"error": "需要登录后才能挂号"}

        dt = parse_datetime(appointment_time)
        if dt is None:
            return {"error": "预约时间格式无效，应为 ISO 格式如 2026-08-22T09:00:00"}
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())

        serializer = AppointmentCreateSerializer(
            data={"doctor": doctor_id, "appointment_time": dt.isoformat(), "reason": reason or ""},
        )
        if not serializer.is_valid():
            return {"error": "挂号失败", "detail": serializer.errors}
        appt = serializer.save(patient=self.user, status=Appointment.STATUS_BOOKED)
        return {
            "ok": True,
            "appointment_id": appt.id,
            "doctor_id": doctor_id,
            "appointment_time": appt.appointment_time.isoformat(),
            "status": appt.status,
        }

    def _tool_get_my_appointments(self) -> Dict[str, Any]:
        from backend.apps.appointments.models import Appointment

        if not (self.user and self.user.is_authenticated):
            return {"error": "需要登录"}
        qs = Appointment.objects.select_related("doctor").filter(patient=self.user).order_by("appointment_time")
        items = [{
            "appointment_id": a.id,
            "doctor": a.doctor.get_full_name() or a.doctor.username,
            "appointment_time": a.appointment_time.isoformat(),
            "reason": a.reason,
            "status": a.status,
        } for a in qs]
        return {"appointments": items, "count": len(items)}
