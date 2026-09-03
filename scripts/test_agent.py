#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""医疗智能体（Agent / Function Calling）演示 + 自测脚本。

用途：
    1. 不需要 API Key 就能验证"工具层"是否正确（直接调 ToolExecutor 打真实数据库）。
    2. 配置了 SILICONFLOW_API_KEY 后，跑完整的 Agent 多步工具调用循环，并打印每一步 trace。

运行：
    python scripts/test_agent.py

演示脚本会在数据库里自动补齐一个 demo 医生 + 排班 + 一个测试病人，
这样"挂号"这条工具链才能真正跑通。
"""
from __future__ import annotations

import os
import sys
from datetime import time as dtime, timedelta
from pathlib import Path

import django
from django.utils import timezone

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend" / "apps"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

django.setup()

from django.contrib.auth.models import Group, User  # noqa: E402
from backend.apps.appointments.models import DoctorProfile, DoctorSchedule  # noqa: E402
from backend.core.llm.agent_tools import ToolExecutor  # noqa: E402


def seed_demo():
    """补齐一个可预约的 demo 医生 + 排班，以及一个测试病人。返回 (patient, doctor_id, date_str)。"""
    doctor, _ = User.objects.get_or_create(username="demo_doctor", defaults={"first_name": "示例", "last_name": "医生"})
    group, _ = Group.objects.get_or_create(name="doctor")
    doctor.groups.add(group)
    DoctorProfile.objects.get_or_create(
        user=doctor,
        defaults={"department": "内科", "hospital": "示范医院", "title": "主治医师", "is_active": True},
    )

    target_date = (timezone.localdate() + timedelta(days=1))
    DoctorSchedule.objects.get_or_create(
        doctor=doctor, schedule_date=target_date, start_time=dtime(9, 0),
        defaults={"end_time": dtime(12, 0), "slot_minutes": 30, "max_appointments_per_slot": 3, "is_active": True},
    )

    patient, _ = User.objects.get_or_create(username="demo_patient", defaults={"first_name": "测试", "last_name": "病人"})
    return patient, doctor.id, target_date.isoformat()


def test_tool_layer(patient, doctor_id, date_str):
    """不依赖大模型，直接验证工具执行层。"""
    print("\n===== [1] 工具层自测（无需 API Key）=====")
    ex = ToolExecutor(user=patient)

    print("\n-- list_doctors(内科) --")
    print(ex.dispatch("list_doctors", {"department": "内科"}))

    print(f"\n-- get_doctor_available_slots(doctor_id={doctor_id}, date={date_str}) --")
    slots = ex.dispatch("get_doctor_available_slots", {"doctor_id": doctor_id, "date": date_str})
    print(slots)

    if slots.get("slots"):
        first = slots["slots"][0]["appointment_time"]
        print(f"\n-- book_appointment(doctor_id={doctor_id}, {first}) --")
        print(ex.dispatch("book_appointment", {"doctor_id": doctor_id, "appointment_time": first, "reason": "自测预约"}))

    print("\n-- get_my_appointments() --")
    print(ex.dispatch("get_my_appointments", {}))

    print("\n-- search_medical_knowledge(高血压) --")
    try:
        print(ex.dispatch("search_medical_knowledge", {"query": "高血压", "top_k": 2}))
    except Exception as e:
        print(f"(知识库检索跳过：{e})")


def test_agent_loop(patient):
    """完整 Agent 循环，需要 SILICONFLOW_API_KEY。"""
    print("\n===== [2] 完整 Agent 多步工具调用 =====")
    if not os.environ.get("SILICONFLOW_API_KEY"):
        print("未检测到 SILICONFLOW_API_KEY，跳过大模型循环。")
        print("配置方式：在项目根目录 .env 写入 SILICONFLOW_API_KEY=sk-xxxx 后重跑。")
        return

    from backend.core.llm.agent import MedicalAgent

    agent = MedicalAgent(user=patient)
    query = "我有点高血压想咨询下，另外帮我看看明天内科有没有号，有的话帮我挂一个"
    print(f"\n用户: {query}")
    result = agent.run(query, lang="zh")

    print(f"\n--- 工具调用轨迹（{len(result['trace'])} 次）---")
    for i, step in enumerate(result["trace"], 1):
        print(f"[{i}] {step['tool']}({step['arguments']})")
        print(f"    -> {step['result']}")
    print(f"\n--- 最终回复（{result['iterations']} 轮）---")
    print(result["answer"])


if __name__ == "__main__":
    patient, doctor_id, date_str = seed_demo()
    test_tool_layer(patient, doctor_id, date_str)
    test_agent_loop(patient)
    print("\n完成。")
