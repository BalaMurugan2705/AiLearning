import json
import statistics
import time
from collections import Counter
from pathlib import Path

from agent.budgets import Budget
from agent.loop import run_agent
from agent.spec import API_VERSIONS, ENDPOINT_NAMES
from eval.week7.run_race import grade_entry

CASES_PATH = Path(__file__).resolve().parent / "cases.json"
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "week8"
RESULTS_PATH = RESULTS_DIR / "trajectory_results.json"

# Same generosity as the week7 race budget: this measures what the agent
# *chooses* to do, not whether it was starved.
EVAL_BUDGET = Budget(max_iterations=8, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=60.0)

# Tools whose arguments are constrained enums (endpoint / api_version) and
# therefore checkable against the ground-truth spec, as opposed to
# search_docs whose only argument is a free-text query.
ARG_BEARING_TOOLS = {"get_openapi_spec", "check_deprecation"}


def extract_tool_calls(transcript: list[dict]) -> list[dict]:
    """Pull every tool call the agent made, in the order it made them, out
    of a RunResult transcript. Each entry is {"name": str, "arguments": dict}.
    """
    calls = []
    for message in transcript:
        for tc in message.get("tool_calls") or []:
            calls.append(
                {
                    "name": tc["function"]["name"],
                    "arguments": json.loads(tc["function"]["arguments"]),
                }
            )
    return calls


def tool_names(tool_calls: list[dict]) -> list[str]:
    return [c["name"] for c in tool_calls]


def _target_mismatch(case: dict, tool_calls: list[dict]) -> bool:
    """True if an arg-bearing call missed the case's named target. The
    api_version half of this only applies when there is exactly one
    arg-bearing call: a case whose accepted sequence checks the endpoint at
    *both* versions (a legitimate before/after comparison) is not a
    mismatch just because one of its two calls used the "other" version --
    that is the whole point of a two-version comparison.
    """
    relevant_endpoint = case.get("relevant_endpoint")
    relevant_api_version = case.get("relevant_api_version")
    if not relevant_endpoint and not relevant_api_version:
        return False

    arg_calls = [c for c in tool_calls if c["name"] in ARG_BEARING_TOOLS]
    enforce_version = relevant_api_version is not None and len(arg_calls) == 1
    for call in arg_calls:
        if relevant_endpoint and call["arguments"].get("endpoint") != relevant_endpoint:
            return True
        if enforce_version and call["arguments"].get("api_version") != relevant_api_version:
            return True
    return False


def trajectory_passes(case: dict, tool_calls: list[dict]) -> bool:
    """A trajectory passes only if the tool-call sequence is one of the
    accepted sequences for this case AND it did not miss the case's named
    target endpoint/api_version (see _target_mismatch). A call using the
    "right kind" of tool but the wrong endpoint is not a pass just because
    the tool name matched.
    """
    names = tool_names(tool_calls)
    if names not in case["accepted_tool_sequences"]:
        return False
    return not _target_mismatch(case, tool_calls)


def classify_failure_mode(case: dict, tool_calls: list[dict]) -> str | None:
    """Name why a trajectory failed, or None if it passed. These names are
    the "zoo": the per-mode regression table groups failing questions by
    the string this returns.
    """
    if trajectory_passes(case, tool_calls):
        return None

    names = tool_names(tool_calls)
    if not names:
        return "no_tool_call"

    allowed_tools = {t for seq in case["accepted_tool_sequences"] for t in seq}
    used_tools = set(names)
    if not used_tools & allowed_tools:
        return "wrong_tool"

    if names in case["accepted_tool_sequences"] and _target_mismatch(case, tool_calls):
        return "wrong_target"

    min_steps = case["min_steps"]
    if len(names) > min_steps:
        return "extra_steps"
    if len(names) < min_steps:
        return "missing_step"
    return "wrong_combination"


def argument_is_valid(call: dict) -> bool:
    """Real vs fluent fiction: does this call's endpoint/api_version name
    something that actually exists in the spec? Only meaningful for
    arg-bearing tools; callers should filter to ARG_BEARING_TOOLS first.
    """
    args = call["arguments"]
    return args.get("endpoint") in ENDPOINT_NAMES and args.get("api_version") in API_VERSIONS


def tool_choice_accuracy(case: dict, tool_calls: list[dict]) -> tuple[int, int]:
    """Returns (correct_calls, total_calls) for one question. A call is
    "correct" if its tool is one that appears in at least one accepted
    sequence for this case -- i.e. it was a legitimate tool to reach for
    here, independent of ordering.
    """
    allowed_tools = {t for seq in case["accepted_tool_sequences"] for t in seq}
    if not tool_calls:
        return (0, 0)
    correct = sum(1 for c in tool_calls if c["name"] in allowed_tools)
    return (correct, len(tool_calls))


def _classify_run_error(exc: Exception) -> str:
    # Real failure seen live on this eval: Groq's own server-side tool-call
    # validation rejects the entire HTTP request (a hard 400, not something
    # call_tool() ever gets a chance to handle) when the model invents a
    # tool name that was never in TOOL_SCHEMAS -- e.g. calling "open_file"
    # instead of search_docs. That is a distinct, nameable failure mode
    # from anything classify_failure_mode() sees, because no transcript is
    # ever returned to inspect.
    if "tool call validation failed" in str(exc):
        return "hallucinated_tool"
    return "api_error"


def run_one(case: dict, client=None) -> dict:
    start = time.monotonic()
    try:
        result = run_agent(case["question"], budget=EVAL_BUDGET, client=client)
    except Exception as exc:
        return {
            "id": case["id"],
            "question": case["question"],
            "answer": None,
            "tool_calls": [],
            "tool_names": [],
            "steps_taken": 0,
            "min_steps": case["min_steps"],
            "outcome_passed": False,
            "trajectory_passed": False,
            "failure_mode": _classify_run_error(exc),
            "tool_choice_correct": 0,
            "tool_choice_total": 0,
            "valid_arg_calls": 0,
            "total_arg_calls": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "wall_seconds": time.monotonic() - start,
            "terminated_by_budget": False,
            "budget_reason": f"error: {exc}",
        }
    tool_calls = extract_tool_calls(result.transcript)
    correct_calls, total_calls = tool_choice_accuracy(case, tool_calls)
    arg_calls = [c for c in tool_calls if c["name"] in ARG_BEARING_TOOLS]
    return {
        "id": case["id"],
        "question": case["question"],
        "answer": result.answer,
        "tool_calls": tool_calls,
        "tool_names": tool_names(tool_calls),
        "steps_taken": len(tool_calls),
        "min_steps": case["min_steps"],
        "outcome_passed": grade_entry(result.answer, case),
        "trajectory_passed": trajectory_passes(case, tool_calls),
        "failure_mode": classify_failure_mode(case, tool_calls),
        "tool_choice_correct": correct_calls,
        "tool_choice_total": total_calls,
        "valid_arg_calls": sum(1 for c in arg_calls if argument_is_valid(c)),
        "total_arg_calls": len(arg_calls),
        "total_tokens": result.total_tokens,
        "total_cost_usd": result.total_cost_usd,
        "wall_seconds": time.monotonic() - start,
        "terminated_by_budget": result.terminated_by_budget,
        "budget_reason": result.budget_reason,
    }


def summarize(records: list[dict]) -> dict:
    if not records:
        return {}
    tool_choice_correct = sum(r["tool_choice_correct"] for r in records)
    tool_choice_total = sum(r["tool_choice_total"] for r in records)
    valid_args = sum(r["valid_arg_calls"] for r in records)
    total_args = sum(r["total_arg_calls"] for r in records)
    costs = [r["total_cost_usd"] for r in records]
    outcome_pass_rate = sum(1 for r in records if r["outcome_passed"]) / len(records)
    trajectory_pass_rate = sum(1 for r in records if r["trajectory_passed"]) / len(records)
    return {
        "n": len(records),
        "tool_choice_accuracy": tool_choice_correct / tool_choice_total if tool_choice_total else None,
        "argument_validity_rate": valid_args / total_args if total_args else None,
        "step_efficiency": statistics.mean(r["steps_taken"] / r["min_steps"] for r in records),
        "cost_p50_usd": statistics.median(costs),
        "cost_max_usd": max(costs),
        "outcome_pass_rate": outcome_pass_rate,
        "trajectory_pass_rate": trajectory_pass_rate,
        "outcome_minus_trajectory_gap": outcome_pass_rate - trajectory_pass_rate,
    }


def mode_counts(records: list[dict]) -> Counter:
    return Counter(r["failure_mode"] for r in records if r["failure_mode"])


def find_gap_examples(records: list[dict]) -> list[dict]:
    """Questions that passed the outcome eval but failed the trajectory
    eval -- the "right answer, wrong path" case the assignment asks us to
    name explicitly.
    """
    return [r for r in records if r["outcome_passed"] and not r["trajectory_passed"]]


def main() -> None:
    cases = json.loads(CASES_PATH.read_text())
    records = [run_one(case) for case in cases]

    summary = summarize(records)
    modes = mode_counts(records)
    gap_examples = find_gap_examples(records)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps({"summary": summary, "modes": dict(modes), "records": records}, indent=2)
    )

    print(json.dumps(summary, indent=2))
    print("Failure modes:", dict(modes))
    print("Gap examples (right answer, wrong path):", [r["id"] for r in gap_examples])
    print(f"Wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
