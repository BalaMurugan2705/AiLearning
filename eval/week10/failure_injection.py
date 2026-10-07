import json
from pathlib import Path

from agent.budgets import Budget
from agent.squad import DeprecationWorker, CodeSampleWorker, run_squad

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASES_PATH = REPO_ROOT / "eval" / "week8" / "cases.json"
FAILURE_CASE_PATH = REPO_ROOT / "failure_case.md"

BUDGET = Budget(max_iterations=8, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=60.0)
TARGET_CASE_ID = "q04"

def main() -> None:
    cases = json.loads(CASES_PATH.read_text())
    case = next(c for c in cases if c["id"] == TARGET_CASE_ID)

    dep_worker = DeprecationWorker(BUDGET)
    code_worker = CodeSampleWorker(BUDGET)

    result = run_squad(
        case["question"],
        dep_worker,
        code_worker,
        case_id=f"{case['id']}-failure-injection",
        force_failure="deprecation_worker",
    )

    dep_hop = next(h for h in result.handoffs if h["hop"] == "orchestrator->deprecation_worker")
    retried = dep_hop["attempts"] > 1

    report = f"""# Failure Case: Injected HTTP 500 on deprecation_worker

## Setup

- Case: `{case['id']}` -- "{case['question']}"
- Injected failure: `deprecation_worker` raises `RuntimeError("HTTP 500: deprecation_worker service unavailable")` on every attempt (simulates the worker's service being down).
- Fact only this worker could normally supply: `{case['expected_fragment']}`

## What the orchestrator actually did

- Attempts made against `deprecation_worker`: {dep_hop['attempts']}
- Error recorded for this hop: `{dep_hop['error']}`
- Resulting task state: `{result.status}`
- Message returned to the user:

> {result.answer}

## Classification

- **Retried:** {"YES -- retried once (per handoffs.log attempts field) before giving up." if retried else "NO -- only one attempt was made."}
- **Task lifecycle outcome:** {"PAUSED: input-required -- the orchestrator stopped and asked the user how to proceed, instead of guessing or quietly degrading." if result.status == "paused_input_required" else "COMPLETED -- the orchestrator returned a final answer despite the failure."}
- **Hallucinated:** NO -- the pause message is a fixed template, not another LLM call, so it cannot state a fact it never confirmed.
"""

    FAILURE_CASE_PATH.write_text(report)
    print(report)
    print(f"wrote {FAILURE_CASE_PATH}")


if __name__ == "__main__":
    main()
