"""
Management command to run RAG evaluation offline.

Usage:
    python manage.py run_eval --type rag --top-k 5 --max-questions 100
    python manage.py run_eval --type rag --mode hard --no-baseline
    python manage.py run_eval --type answer_quality --max-questions 20
    python manage.py run_eval --type full --max-questions 20
"""
from django.core.management.base import BaseCommand
from evaluation.models import EvalRun, EvalResult
from evaluation.services import evaluate_rag_retrieval, evaluate_answer_quality_full, calibrate_judge


class Command(BaseCommand):
    help = "Run professional-grade offline evaluation for RAG retrieval and/or answer quality"

    def add_arguments(self, parser):
        parser.add_argument("--type", type=str, default="rag", choices=["rag", "answer_quality", "full", "calibrate", "test_judge"])
        parser.add_argument("--top-k", type=int, default=5)
        parser.add_argument("--max-questions", type=int, default=100)
        parser.add_argument("--mode", type=str, default="hard",
                            choices=["hard", "smoke", "both"],
                            help="hard=symptom-description (RECOMMENDED), smoke=entity-name (sanity check only), both=run both")
        parser.add_argument("--no-baseline", action="store_true",
                            help="Skip BM25 baseline comparison to save time")
        parser.add_argument("--judge-model", type=str, default="Qwen/Qwen2.5-7B-Instruct",
                            help="LLM model to use as judge (should differ from generation model)")

    def handle(self, *args, **options):
        eval_type = options["type"]
        top_k = options["top_k"]
        max_q = options["max_questions"]
        eval_mode = options.get("mode", "hard")
        include_baseline = not options.get("no_baseline", False)
        judge_model = options.get("judge_model", "Qwen/Qwen2.5-7B-Instruct")

        if eval_type == "calibrate":
            self._run_calibration(judge_model, max_q)
            return

        if eval_type == "test_judge":
            self._test_judge(judge_model)
            return

        if eval_type in ("rag", "full"):
            msg = f"RAG Retrieval Evaluation (mode={eval_mode}, top_k={top_k}, max_q={max_q}"
            if include_baseline:
                msg += ", with BM25 baseline"
            msg += ")"
            self.stdout.write(self.style.NOTICE(msg))

            result = evaluate_rag_retrieval(
                top_k=top_k,
                max_questions=max_q,
                eval_mode=eval_mode,
                include_baseline=include_baseline,
            )

            if result.get("error"):
                self.stdout.write(self.style.ERROR(f"Eval failed: {result['error']}"))
                return

            primary = result.get("hard") or result.get("smoke") or {}
            baseline = result.get("hard_bm25_baseline")

            self._print_retrieval_results(primary, "BGE-M3 (vector)")
            if baseline:
                self._print_retrieval_results(baseline, "BM25  (keyword)")
                self._print_comparison(primary, baseline)

            if primary.get("by_category"):
                self._print_category_breakdown(primary["by_category"])

            per_questions = primary.get("per_question", [])
            run = EvalRun.objects.create(
                eval_type="rag_retrieval",
                eval_mode=eval_mode,
                status="completed",
                top_k=top_k,
                total_questions=primary.get("total_questions", 0),
                total_relevant=primary.get("total_relevant_found", 0),
                recall_at_1=primary.get("recall_at_1", 0.0),
                recall_at_3=primary.get("recall_at_3", 0.0),
                recall_at_5=primary.get("recall_at_5", 0.0),
                mrr=primary.get("mrr", 0.0),
                ndcg_at_5=primary.get("ndcg_at_5", 0.0),
                recall_at_1_ci=primary.get("recall_at_1_ci") or {},
                recall_at_5_ci=primary.get("recall_at_5_ci") or {},
                mrr_ci=primary.get("mrr_ci") or {},
                bm25_recall_at_1=baseline.get("recall_at_1") if baseline else None,
                bm25_recall_at_5=baseline.get("recall_at_5") if baseline else None,
                bm25_mrr=baseline.get("mrr") if baseline else None,
                bm25_ndcg_at_5=baseline.get("ndcg_at_5") if baseline else None,
            )
            for pq in per_questions:
                EvalResult.objects.create(
                    run=run,
                    question=pq["question"],
                    expected_entity_keys=pq["expected_entity_keys"],
                    retrieved_ranks=pq.get("ranks", []),
                    top_score=pq.get("top_score", 0.0),
                    is_relevant_found=pq.get("is_relevant_found", False),
                    first_relevant_rank=pq.get("first_relevant_rank"),
                )
            self.stdout.write(self.style.SUCCESS(f"Saved as EvalRun id={run.id}"))

        if eval_type in ("answer_quality", "full"):
            self.stdout.write(self.style.NOTICE(f"Answer Quality Evaluation (max_q={max_q}, judge={judge_model})"))
            result = evaluate_answer_quality_full(max_questions=max_q, judge_model=judge_model)

            if result.get("error"):
                self.stdout.write(self.style.ERROR(f"Eval failed: {result['error']}"))
            elif result["total_questions"] == 0:
                self.stdout.write(self.style.WARNING("No eval pairs found."))
            else:
                self.stdout.write(f"  Total questions:    {result['total_questions']}")
                for d in ["accuracy", "completeness", "relevance", "faithfulness", "safety"]:
                    key = f"avg_{d}"
                    if key in result:
                        self.stdout.write(f"  Avg {d:15s}: {result[key]:.2f}/5")

                acc_ci = result.get("accuracy_ci") or {}
                if acc_ci.get("ci_lower") is not None:
                    self.stdout.write(f"  Accuracy 95% CI:    [{acc_ci['ci_lower']:.2f}, {acc_ci['ci_upper']:.2f}]")

                run = EvalRun.objects.create(
                    eval_type="answer_quality",
                    status="completed",
                    top_k=5,
                    total_questions=result["total_questions"],
                    avg_accuracy=result.get("avg_accuracy"),
                    avg_completeness=result.get("avg_completeness"),
                    avg_relevance=result.get("avg_relevance"),
                    avg_faithfulness=result.get("avg_faithfulness"),
                    avg_safety=result.get("avg_safety"),
                    judge_model=judge_model,
                )
                for pq in result.get("per_question", []):
                    EvalResult.objects.create(
                        run=run,
                        question=pq["question"],
                        expected_entity_keys=pq.get("expected_entity_keys", []),
                        is_relevant_found=pq.get("is_relevant_found", False),
                        generated_answer=pq.get("answer", ""),
                        accuracy_score=pq.get("accuracy"),
                        completeness_score=pq.get("completeness"),
                        relevance_score=pq.get("relevance"),
                        faithfulness_score=pq.get("faithfulness"),
                        safety_score=pq.get("safety"),
                        judge_raw=pq.get("judge_raw", {}),
                    )
                self.stdout.write(self.style.SUCCESS(f"Saved as EvalRun id={run.id}"))

        self.stdout.write(self.style.SUCCESS("Evaluation complete."))

    def _print_retrieval_results(self, data: dict, label: str):
        total = data.get("total_questions", 0)
        self.stdout.write(f"\n  ── {label} ({total} questions) ──")
        self.stdout.write(f"  Recall@1:   {data.get('recall_at_1', 0):.4f}")
        self.stdout.write(f"  Recall@3:   {data.get('recall_at_3', 0):.4f}")
        self.stdout.write(f"  Recall@5:   {data.get('recall_at_5', 0):.4f}")
        self.stdout.write(f"  MRR:        {data.get('mrr', 0):.4f}")
        self.stdout.write(f"  NDCG@5:     {data.get('ndcg_at_5', 0):.4f}")

        r1_ci = data.get("recall_at_1_ci") or {}
        if r1_ci.get("ci_lower") is not None:
            self.stdout.write(f"  Recall@1 95% CI: [{r1_ci['ci_lower']:.4f}, {r1_ci['ci_upper']:.4f}]")
        r5_ci = data.get("recall_at_5_ci") or {}
        if r5_ci.get("ci_lower") is not None:
            self.stdout.write(f"  Recall@5 95% CI: [{r5_ci['ci_lower']:.4f}, {r5_ci['ci_upper']:.4f}]")

        self.stdout.write(f"  Relevant found: {data.get('total_relevant_found', 0)}/{total}")

    def _print_comparison(self, primary: dict, baseline: dict):
        self.stdout.write(f"\n  ── BGE-M3 vs BM25 Comparison ──")
        delta_recall5 = primary.get("recall_at_5", 0) - baseline.get("recall_at_5", 0)
        delta_mrr = primary.get("mrr", 0) - baseline.get("mrr", 0)
        self.stdout.write(f"  Recall@5 delta:  {delta_recall5:+.4f}  ({'BGE-M3 wins' if delta_recall5 > 0 else 'BM25 wins' if delta_recall5 < 0 else 'Tie'})")
        self.stdout.write(f"  MRR delta:       {delta_mrr:+.4f}  ({'BGE-M3 wins' if delta_mrr > 0 else 'BM25 wins' if delta_mrr < 0 else 'Tie'})")

    def _print_category_breakdown(self, by_category: dict):
        self.stdout.write(f"\n  ── Per-Category Breakdown ──")
        for cat, stats in sorted(by_category.items()):
            self.stdout.write(f"  {cat:20s}  n={stats['total']:3d}  Recall@5={stats['recall_at_5']:.4f}  MRR={stats['mrr']:.4f}")

    def _run_calibration(self, judge_model: str, max_samples: int):
        self.stdout.write(self.style.NOTICE(f"Judge Calibration (model={judge_model}, max_samples={max_samples})"))
        self.stdout.write("  Running LLM judge against human-annotated gold set...")
        self.stdout.write("  This validates whether the judge score correlates with human expert judgment.")

        result = calibrate_judge(judge_model=judge_model, max_samples=max_samples)

        if result.get("error"):
            self.stdout.write(self.style.ERROR(f"Calibration failed: {result['error']}"))
            return

        self.stdout.write(f"\n  ── Calibration Results ──")
        self.stdout.write(f"  Samples:           {result.get('calibrated_samples', 0)}")
        self.stdout.write(f"  Failed calls:      {result.get('failed_calls', 0)}")

        parse_failures = result.get("parse_failures", [])
        if parse_failures:
            self.stdout.write(self.style.WARNING(f"\n  ── Parse Failures (first {len(parse_failures)}) ──"))
            for pf in parse_failures:
                self.stdout.write(f"  Q: {pf['question']}")
                self.stdout.write(f"  Error: {pf['error']}")
                self.stdout.write(f"  Raw: {pf['raw'][:200]}")
                self.stdout.write("  ---")

        self.stdout.write(f"  Avg Pearson r:     {result.get('avg_pearson_r', 0):.4f}")
        self.stdout.write(f"  Verdict:           {result.get('verdict', 'N/A')}")

        corr = result.get("correlation", {})
        for dim, stats in sorted(corr.items()):
            r = stats.get("pearson_r", 0)
            mae = stats.get("mae", 0)
            n = stats.get("n_pairs", 0)
            gold_m = stats.get("gold_mean", 0)
            judge_m = stats.get("judge_mean", 0)
            indicator = "+++" if r > 0.7 else ("++" if r > 0.5 else ("+" if r > 0.3 else "-"))
            self.stdout.write(f"  {dim:15s}  r={r:+.4f}  MAE={mae:.2f}  n={n}  gold_avg={gold_m:.1f}  judge_avg={judge_m:.1f}  {indicator}")

        run = EvalRun.objects.create(
            eval_type="answer_quality",
            eval_mode="judge_calibration",
            status="completed",
            total_questions=result.get("calibrated_samples", 0),
            judge_model=judge_model,
            judge_calibration=corr,
            extra={"verdict": result.get("verdict", ""), "avg_pearson_r": result.get("avg_pearson_r", 0)},
        )
        self.stdout.write(self.style.SUCCESS(f"\n  Saved as EvalRun id={run.id}"))

    def _test_judge(self, judge_model: str):
        """Quick test: judge a single answer against the gold set to verify API works."""
        from evaluation.services import _load_gold_set, judge_answer_quality, _build_dimensions_text, LLM_JUDGE_PROMPT

        gold = _load_gold_set()
        if not gold:
            self.stdout.write(self.style.ERROR("No gold set found"))
            return

        item = gold[0]
        self.stdout.write(self.style.NOTICE(f"Testing judge ({judge_model}) on first gold set sample:"))

        question = item["question"]
        answer = item["answer"]
        context = item.get("context", "")
        gs = item.get("gold_scores", {})

        self.stdout.write(f"  Q: {question}")
        self.stdout.write(f"  A: {answer[:150]}...")
        self.stdout.write(f"  Gold scores: {gs}")
        self.stdout.write(f"")

        result = judge_answer_quality(question, answer, context, judge_model=judge_model, verbose=True)

        self.stdout.write(f"\n  ── Judge Result ──")
        for d in ["accuracy", "completeness", "relevance", "faithfulness", "safety"]:
            self.stdout.write(f"  {d}: {result.get(d)} (gold: {gs.get(d)})")
        if result.get("error"):
            self.stdout.write(self.style.ERROR(f"  Error: {result['error']}"))
            self.stdout.write(f"  Raw response: {(result.get('raw') or '')[:500]}")
        if result.get("comment"):
            self.stdout.write(f"  Comment: {result['comment']}")
