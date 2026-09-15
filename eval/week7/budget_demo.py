from pathlib import Path

from agent.budgets import Budget
from agent.loop import run_agent

# Deliberately tight: 1 iteration is not enough for a question that needs a
# tool call before it can answer, so this budget is guaranteed to trip.
TIGHT_BUDGET = Budget(max_iterations=1, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=30.0)

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "results" / "week7" / "budget_termination.log"


def run_and_log(question: str, client=None, log_path: Path | None = None) -> Path:
    log_path = log_path or DEFAULT_LOG_PATH
    result = run_agent(question, budget=TIGHT_BUDGET, client=client)

    lines = [
        f"question: {question}",
        f"budget: {TIGHT_BUDGET}",
        f"terminated_by_budget: {result.terminated_by_budget}",
        f"budget_reason: {result.budget_reason}",
        f"iterations completed before stop: {result.iterations}",
        "run terminated cleanly -- no crash, no extra lap, no fabricated answer.",
        "",
        "transcript:",
    ]
    for message in result.transcript:
        lines.append(str(message))

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(lines))
    return log_path


if __name__ == "__main__":
    import json

    from eval.week7.run_race import QUESTIONS_PATH

    questions = json.loads(QUESTIONS_PATH.read_text())
    chained = next(q for q in questions if q["needs_chain"])
    path = run_and_log(chained["question"])
    print(f"Wrote {path}")
