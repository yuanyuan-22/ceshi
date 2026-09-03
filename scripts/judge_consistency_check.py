"""
LLM-as-Judge 一致性校验脚本

用法：
    python scripts/judge_consistency_check.py

流程：
    1. 从知识库取 15-20 条实体，自动生成问答对
    2. 用 Qwen 生成回答
    3. 记录 LLM 打分
    4. 提示用户手动输入自己的评分 (1-5)
    5. 对比人工 vs LLM 打分，输出 Pearson 相关系数
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from backend.apps.evaluation.services import judge_answer_quality
from backend.core.rag.kb import get_kb
from backend.core.llm.qa_siliconflow import get_qa_generator


HUMAN_COMPARISON_PROMPT = """
题目 {idx}: {question}

AI 回答:
{answer}

请对回答在 1(最差) 到 5(最好) 范围内打分：
  accuracy (准确性): 医学信息是否正确？有无幻觉？
  completeness (完整性): 是否覆盖了关键信息？
  relevance (相关性): 是否直接回答了问题？

输入格式: accuracy completeness relevance
例如: 4 3 5
你的评分: """


def main():
    kb = get_kb()
    generator = get_qa_generator()

    test_cases = [
        {"question": "感冒和流感有什么区别", "lang": "zh"},
        {"question": "发烧多少度需要去医院", "lang": "zh"},
        {"question": "高血压患者能不能喝酒", "lang": "zh"},
        {"question": "抗生素和消炎药是不是一回事", "lang": "zh"},
        {"question": "糖尿病饮食要注意什么", "lang": "zh"},
        {"question": "What are the symptoms of dehydration", "lang": "en"},
        {"question": "How to treat a mild burn at home", "lang": "en"},
        {"question": "What causes high blood pressure", "lang": "en"},
        {"question": "头疼应该挂什么科", "lang": "zh"},
        {"question": "体检报告上转氨酶偏高是什么意思", "lang": "zh"},
    ]

    results = []
    print(f"正在运行 {len(test_cases)} 条测试...")
    print("=" * 60)

    for idx, case in enumerate(test_cases, 1):
        question = case["question"]
        requested_lang = case.get("lang", "zh")

        hits = kb.search(question, top_k=5, preferred_langs=[requested_lang, "zh", "en"])
        context_list = []
        for h in hits[:3]:
            text = (h.get("explain_text") or h.get("text") or "").strip()
            if text:
                context_list.append(text)
        context = "\n\n".join(context_list)

        if not context:
            answer = "知识库中没有找到相关信息。"
        else:
            answer = generator.generate(
                prompt="", context=context, question=question,
                lang=requested_lang, max_tokens=500, temperature=0.3,
            )

        judge = judge_answer_quality(question, answer, context)

        print(f"\n{'='*60}")
        print(HUMAN_COMPARISON_PROMPT.format(idx=idx, question=question, answer=answer))

        while True:
            try:
                line = input().strip()
                parts = line.split()
                if len(parts) != 3:
                    print("请按格式输入 3 个数字: accuracy completeness relevance")
                    continue
                h_acc, h_comp, h_rel = int(parts[0]), int(parts[1]), int(parts[2])
                if not all(1 <= v <= 5 for v in [h_acc, h_comp, h_rel]):
                    print("分数必须在 1-5 之间")
                    continue
                break
            except (ValueError, EOFError):
                print("输入无效，请重试")
                continue

        results.append({
            "question": question,
            "answer": answer[:200],
            "human": {"accuracy": h_acc, "completeness": h_comp, "relevance": h_rel},
            "llm": {"accuracy": judge.get("accuracy", 3), "completeness": judge.get("completeness", 3), "relevance": judge.get("relevance", 3)},
        })

        diff = abs(h_acc - judge.get("accuracy", 3)) + abs(h_comp - judge.get("completeness", 3)) + abs(h_rel - judge.get("relevance", 3))
        if diff <= 2:
            print(f"  ✓ 一致性较好 (差异={diff})")
        else:
            print(f"  △ 差异较大 (差异={diff})")

    # 输出结果
    print("\n\n" + "=" * 60)
    print("一致性校验结果汇总")
    print("=" * 60)
    print(f"{'题目':<30} {'人工A':>3} {'LLMA':>3} {'人工C':>3} {'LLMC':>3} {'人工R':>3} {'LLMR':>3} {'差异':>4}")
    print("-" * 60)

    total_diff = 0
    human_scores = {"accuracy": [], "completeness": [], "relevance": []}
    llm_scores = {"accuracy": [], "completeness": [], "relevance": []}

    for r in results:
        h = r["human"]
        l = r["llm"]
        diff = abs(h["accuracy"] - l["accuracy"]) + abs(h["completeness"] - l["completeness"]) + abs(h["relevance"] - l["relevance"])
        total_diff += diff
        short_q = r["question"][:28]
        print(f"{short_q:<30} {h['accuracy']:>3} {l['accuracy']:>3} {h['completeness']:>3} {l['completeness']:>3} {h['relevance']:>3} {l['relevance']:>3} {diff:>4}")
        for dim in ["accuracy", "completeness", "relevance"]:
            human_scores[dim].append(h[dim])
            llm_scores[dim].append(l[dim])

    print("-" * 60)
    avg_diff = total_diff / max(1, len(results))
    print(f"平均每题差异: {avg_diff:.2f} / 15")

    for dim in ["accuracy", "completeness", "relevance"]:
        h = human_scores[dim]
        l = llm_scores[dim]
        if len(h) >= 3:
            n = len(h)
            h_mean = sum(h) / n
            l_mean = sum(l) / n
            cov = sum((h[i] - h_mean) * (l[i] - l_mean) for i in range(n))
            h_var = sum((x - h_mean) ** 2 for x in h)
            l_var = sum((x - l_mean) ** 2 for x in l)
            denom = math.sqrt(h_var * l_var)
            pearson = cov / denom if denom > 0 else 0
            print(f"{dim}:   人工均值={h_mean:.2f}  LLM均值={l_mean:.2f}  Pearson r={pearson:.3f}")

    with open("judge_consistency_results.json", "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=2)
    print(f"\n详情已保存到 judge_consistency_results.json")


if __name__ == "__main__":
    main()
