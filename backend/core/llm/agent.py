# backend/core/llm/agent.py
"""医疗智能体：在大模型之上加一层"工具调用"循环（ReAct 式 tool-use loop）。

与 SiliconFlowQA（被动检索问答）不同，Agent 能自主决定：
    - 什么时候查知识库
    - 什么时候查医生 / 号源
    - 什么时候真正下单挂号
并把多步工具结果汇总成一句自然语言回复。

用法：
    agent = MedicalAgent(user=request.user)
    result = agent.run("帮我查下高血压，然后挂个内科的号")
    # result -> {"answer": "...", "trace": [...], "iterations": n}
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from backend.core.llm.agent_tools import TOOLS_SPEC, ToolExecutor
from backend.core.llm.qa_siliconflow import get_client

import os

# 智能体必须用"支持 Function Calling / tool_calls"的模型。
# 实测：SiliconFlow 上 Qwen2.5-7B-Instruct 不会返回 tool_calls（会把调用当普通文本吐出来），
# 72B 才会规范返回 tool_calls。可用环境变量 AGENT_MODEL 覆盖。
AGENT_MODEL = os.environ.get("AGENT_MODEL", "Qwen/Qwen2.5-72B-Instruct")


LANGUAGE_NAMES = {
    "zh": "Simplified Chinese",
    "en": "English",
    "ja": "Japanese",
    "fr": "French",
    "de": "German",
}


def _system_prompt(lang: str, today: str) -> str:
    answer_language = LANGUAGE_NAMES.get(lang, LANGUAGE_NAMES["zh"])
    return (
        "You are a medical assistant agent for a hospital platform. "
        f"Today's date is {today}. "
        f"Always answer the user in {answer_language}. "
        "You can call tools to search the medical knowledge base and to manage appointments.\n"
        "Rules:\n"
        "1. For medical questions, call search_medical_knowledge and answer ONLY from what it returns. "
        "If it returns nothing useful, say the knowledge base cannot answer reliably and advise seeing a doctor in person. Never invent facts.\n"
        "2. To book an appointment you MUST first call list_doctors, then get_doctor_available_slots, "
        "and only then book_appointment with a slot that actually exists. Never fabricate a doctor_id or a time.\n"
        "3. If information needed for booking is missing (which doctor, which day), ask the user instead of guessing.\n"
        "4. Medical answers are for reference only; always remind the user to consult a licensed doctor for diagnosis.\n"
        "5. Keep replies concise and easy to read."
    )


class MedicalAgent:
    def __init__(self, user, model: str = AGENT_MODEL, max_iters: int = 5):
        self.user = user
        self.model = model
        self.max_iters = max_iters
        self.client = get_client()
        self.executor = ToolExecutor(user)

    def run(self, message: str, lang: str = "zh") -> Dict[str, Any]:
        if not self.client:
            return {"answer": "智能体服务不可用：未配置大模型 API 客户端（SILICONFLOW_API_KEY）。",
                    "trace": [], "iterations": 0, "error": "no_client"}

        from django.utils import timezone
        today = timezone.localdate().isoformat()

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": _system_prompt(lang, today)},
            {"role": "user", "content": message},
        ]
        trace: List[Dict[str, Any]] = []

        for i in range(self.max_iters):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=TOOLS_SPEC,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=700,
                )
            except Exception as e:
                return {"answer": f"智能体调用大模型失败：{e}", "trace": trace, "iterations": i, "error": str(e)}

            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)

            # 没有工具调用 -> 模型给出最终回答，循环结束
            if not tool_calls:
                return {"answer": (msg.content or "").strip(), "trace": trace, "iterations": i + 1}

            # 回填 assistant 的 tool_calls 消息，供下一轮上下文使用
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })

            # 逐个执行工具并把结果回填给模型
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self.executor.dispatch(name, args)
                trace.append({"tool": name, "arguments": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        # 到达最大轮数仍未收敛：再逼一次最终回答（这次不再给工具）
        try:
            final = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=0.2, max_tokens=700,
            )
            answer = (final.choices[0].message.content or "").strip()
        except Exception as e:
            answer = f"智能体已完成工具调用，但生成最终回复失败：{e}"
        return {"answer": answer, "trace": trace, "iterations": self.max_iters}
