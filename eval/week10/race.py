import json
import statistics
from pathlib import Path

from agent.budgets import Budget
from agent.loop import run_agent
from agent.squad import DeprecationWorker, CodeSampleWorker, run_squad
from eval.week7.run_race import grade_entry
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASES_PATH = REPO_ROOT / "eval" / "week8" / "cases.json"
RACE_TABLE_PATH = REPO_ROOT / "race_table.md"
HANDOFFS_LOG_PATH = REPO_ROOT / "handoffs.log"

RACE_BUDGET = Budget(max_iterations=8, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=60.0)


def percentile(values: list[float], pct: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)

def attribute_bottleneck(handoffs_log_path: Path) -> tuple[str, float]:
    totals = defaultdict(int)
    grand_total = 0
    with handoffs_log_path.open(encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            totals[entry["hop"]] += entry["tokens"]
            grand_total += entry["tokens"]
    bottleneck_hop, bottleneck_tokens = max(totals.items(), key=lambda kv: kv[1])
    return bottleneck_hop, bottleneck_tokens / grand_total


def run_single_agent_arm(cases: list[dict]) -> list[dict]:
    records = []
    for case in cases:
        result = run_agent(case["question"], budget=RACE_BUDGET)
        records.append({
            "id": case["id"],
            "passed": grade_entry(result.answer, case),
            "total_tokens": result.total_tokens,
            "total_cost_usd": result.total_cost_usd,
            "wall_seconds": result.wall_seconds,
        })
    return records


def run_squad_arm(cases: list[dict]) -> list[dict]:
    records = []
    for case in cases:
        dep_worker = DeprecationWorker(RACE_BUDGET)
        code_worker = CodeSampleWorker(RACE_BUDGET)
        result = run_squad(case["question"], dep_worker, code_worker, case_id=case["id"])
        records.append({
            "id": case["id"],
            "passed": grade_entry(result.answer, case),
            "total_tokens": result.total_tokens,
            "total_cost_usd": result.total_cost_usd,
            "wall_seconds": result.wall_seconds,
        })
    return records


def summarize(records: list[dict]) -> dict:
    n = len(records)
    latencies = [r["wall_seconds"] for r in records]
    return {
        "n": n,
        "pass_rate": sum(1 for r in records if r["passed"]) / n,
        "p50_latency_s": percentile(latencies, 0.50),
        "p99_latency_s": percentile(latencies, 0.99),
        "total_tokens": sum(r["total_tokens"] for r in records),
        "cost_per_question_usd": sum(r["total_cost_usd"] for r in records) / n,
    }


def render_table(single: dict, squad: dict) -> str:
    multiplier = squad["total_tokens"] / single["total_tokens"]
    lines = [
        "# Race Table: Single Agent vs. Orchestrator Squad",
        "",
        "10 cases from `eval/week8/cases.json` (used in place of the task "
        "doc's \"Week-6 cases\" -- see `task/W10-progress-log.md` for why), "
        "same model (openai/gpt-oss-120b) for both arms, same deterministic "
        "grader (`eval/week7/run_race.py::grade_entry`).",
        "",
        "| Metric | Single Agent | Orchestrator Squad |",
        "| --- | --- | --- |",
        f"| Pass rate | {single['pass_rate']:.0%} "
        f"({round(single['pass_rate']*single['n'])}/{single['n']}) | "
        f"{squad['pass_rate']:.0%} "
        f"({round(squad['pass_rate']*squad['n'])}/{squad['n']}) |",
        f"| p50 latency (s) | {single['p50_latency_s']:.2f} | {squad['p50_latency_s']:.2f} |",
        f"| p99 latency (s) | {single['p99_latency_s']:.2f} | {squad['p99_latency_s']:.2f} |",
        f"| Total tokens | {single['total_tokens']} | {squad['total_tokens']} |",
        f"| Cost per question (USD) | ${single['cost_per_question_usd']:.5f} | "
        f"${squad['cost_per_question_usd']:.5f} |",
        "",
        f"**Context Re-Send Multiplier:** {multiplier:.1f}x "
        f"({squad['total_tokens']} squad tokens / {single['total_tokens']} single-agent tokens)",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    cases = json.loads(CASES_PATH.read_text())

    # Start handoffs.log fresh so its line count matches this run's totals.
    HANDOFFS_LOG_PATH.write_text("")

    single_records = run_single_agent_arm(cases)
    squad_records = run_squad_arm(cases)

    single_summary = summarize(single_records)
    squad_summary = summarize(squad_records)

    bottleneck_hop, bottleneck_share = attribute_bottleneck(HANDOFFS_LOG_PATH)
    table = render_table(single_summary, squad_summary)
    table += (
        f"\n**Largest hand-off bottleneck:** `{bottleneck_hop}` -- "
        f"{bottleneck_share:.0%} of all squad tokens across the 10 cases.\n"
    )
    RACE_TABLE_PATH.write_text(table)

    print(json.dumps({"single": single_summary, "squad": squad_summary}, indent=2))
    print(f"wrote {RACE_TABLE_PATH}")
    print(f"wrote {HANDOFFS_LOG_PATH}")


if __name__ == "__main__":
    main()
