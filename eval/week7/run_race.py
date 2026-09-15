import csv
import json
import statistics
import time
from pathlib import Path

from agent.budgets import Budget
from agent.loop import run_agent
from agent.workflow import run_workflow

QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.json"
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "week7"
RACE_CSV_PATH = RESULTS_DIR / "race.csv"
RACE_DETAILS_PATH = RESULTS_DIR / "race_details.json"

# Generous on purpose: the race measures how much the agent *chooses* to
# spend, not whether we starved it. The budget demo script is where a
# budget is deliberately made tight.
RACE_BUDGET = Budget(max_iterations=8, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=60.0)


# The model answers with "smart" typography (narrow no-break spaces,
# non-breaking hyphens, curly quotes) that a raw substring check misses
# even when the fact stated is exactly right -- e.g. "400 KB" is not
# an ASCII-substring match for "400 KB". Normalizing both sides to plain
# ASCII equivalents before comparing keeps the check honest about content
# instead of penalizing the model's punctuation style. Written as explicit
# \u escapes, not raw glyphs, so the exact codepoint is never ambiguous.
_TYPOGRAPHIC_EQUIVALENTS = {
    "‐": "-",  # hyphen
    "‑": "-",  # non-breaking hyphen (seen in model output, e.g. "pre‑armed")
    "–": "-",  # en dash
    "—": "-",  # em dash
    " ": " ",  # no-break space
    " ": " ",  # narrow no-break space (seen in model output, e.g. "400 KB")
    "‘": "'",  # left curly single quote
    "’": "'",  # right curly single quote
    "“": '"',  # left curly double quote
    "”": '"',  # right curly double quote
}


def _normalize(text: str) -> str:
    for special, plain in _TYPOGRAPHIC_EQUIVALENTS.items():
        text = text.replace(special, plain)
    return text


def grade(answer: str | None, expected_fragment: str) -> bool:
    if answer is None:
        return False
    return _normalize(expected_fragment.lower()) in _normalize(answer.lower())


# Any one of these appearing in an answer counts as an honest refusal,
# used for golden-set questions with no fact to grade against (see
# eval/week7/golden_questions.py's is_negative_case entries).
REFUSAL_KEYWORDS = [
    "not provided",
    "not contain",  # covers both "does not contain" and "do not contain"
    "no information",
    "cannot find",
    "cannot answer",
    "not available",
    "not covered",
    "not present",
    "not mention",  # covers "not mentioned", "does not mention", "doesn't mention"
    "no details",
    "outside the",
    "don't know",
    "do not know",
    "don't have",  # e.g. "I don't have the information needed to answer that"
    "do not have",
]


def grade_refusal(answer: str | None) -> bool:
    if answer is None:
        return False
    normalized = _normalize(answer.lower())
    return any(_normalize(keyword) in normalized for keyword in REFUSAL_KEYWORDS)


def grade_entry(answer: str | None, entry: dict) -> bool:
    """Like grade(), but dispatches to grade_refusal() for a negative-case
    entry (one with no fact to check, only an expectation to admit "not in
    the docs"). Falls back to grade() for every ordinary entry, including
    eval/week7/questions.json's, which never set is_negative_case at all.
    """
    if entry.get("is_negative_case"):
        return grade_refusal(answer)
    fragment = entry["expected_fragment"]
    if isinstance(fragment, list):
        # A correct answer can be phrased more than one reasonable way
        # (e.g. "unconditionally" vs "regardless of visibility") -- any one
        # of these substrings appearing counts as a pass.
        return any(grade(answer, f) for f in fragment)
    return grade(answer, fragment)


def aggregate(records: list[dict]) -> dict:
    if not records:
        return {"pass_rate": 0.0, "p50_latency_seconds": 0.0, "total_tokens": 0, "cost_per_question_usd": 0.0}
    passed = sum(1 for r in records if r["passed"])
    latencies = [r["wall_seconds"] for r in records]
    total_tokens = sum(r["total_tokens"] for r in records)
    total_cost = sum(r["total_cost_usd"] for r in records)
    return {
        "pass_rate": passed / len(records),
        "p50_latency_seconds": statistics.median(latencies),
        "total_tokens": total_tokens,
        "cost_per_question_usd": total_cost / len(records),
    }


def run_system(run_fn, questions: list[dict]) -> list[dict]:
    """Shared by this module's main() and run_golden_race.py: run one
    system (run_agent or run_workflow) over a list of question entries and
    grade each answer. A question entry needs at least {id, question,
    needs_chain} plus either expected_fragment or is_negative_case=True.

    One question's API error (seen live: Groq occasionally rejects a
    response outright with "output_parse_failed" when the model emits raw
    reasoning text instead of a clean answer) does not abort the batch --
    it's recorded as a failed, zero-cost record and the race continues.
    Without this, a single bad generation loses every already-completed
    result in the run and burns real API quota again on a from-scratch
    retry.
    """
    records = []
    for q in questions:
        start = time.monotonic()
        try:
            if run_fn is run_agent:
                result = run_fn(q["question"], budget=RACE_BUDGET)
            else:
                result = run_fn(q["question"])
        except Exception as exc:
            records.append(
                {
                    "id": q["id"],
                    "question": q["question"],
                    "needs_chain": q["needs_chain"],
                    "answer": None,
                    "terminated_by_budget": False,
                    "budget_reason": f"error: {exc}",
                    "passed": False,
                    "wall_seconds": time.monotonic() - start,
                    "total_tokens": 0,
                    "total_cost_usd": 0.0,
                }
            )
            continue
        records.append(
            {
                "id": q["id"],
                "question": q["question"],
                "needs_chain": q["needs_chain"],
                "answer": result.answer,
                "terminated_by_budget": result.terminated_by_budget,
                "budget_reason": result.budget_reason,
                "passed": grade_entry(result.answer, q),
                "wall_seconds": result.wall_seconds,
                "total_tokens": result.total_tokens,
                "total_cost_usd": result.total_cost_usd,
            }
        )
    return records


def write_race_results(csv_path: Path, details_path: Path, agent_records: list[dict], workflow_records: list[dict]) -> None:
    agent_stats = aggregate(agent_records)
    workflow_stats = aggregate(workflow_records)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["system", "pass_rate", "p50_latency_seconds", "total_tokens", "cost_per_question_usd"])
        for name, stats in [("agent", agent_stats), ("workflow", workflow_stats)]:
            writer.writerow([name, stats["pass_rate"], stats["p50_latency_seconds"], stats["total_tokens"], stats["cost_per_question_usd"]])

    details_path.write_text(json.dumps({"agent": agent_records, "workflow": workflow_records}, indent=2))

    print(f"Wrote {csv_path}")
    print(f"Wrote {details_path}")


def main() -> None:
    questions = json.loads(QUESTIONS_PATH.read_text())
    agent_records = run_system(run_agent, questions)
    workflow_records = run_system(run_workflow, questions)
    write_race_results(RACE_CSV_PATH, RACE_DETAILS_PATH, agent_records, workflow_records)


if __name__ == "__main__":
    main()
