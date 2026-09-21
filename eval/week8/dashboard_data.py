"""Loads the Week 8 trajectory-eval artifacts (results/week8/*.json) into
plain data structures for the /week8 dashboard route in app.py.

Kept dependency-free from FastAPI/Jinja2 on purpose -- this module only
reads and shapes data, so it's testable without spinning up the web app.
"""
import json
import statistics
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "week8"

# Fixed snapshots from the actual live runs described in results/week8/results.md,
# not the scratch file (trajectory_results.json) that a fresh eval run overwrites.
BEFORE_FILES = ["trajectory_results_before.json", "trajectory_results_before2.json"]
AFTER_FILES = [
    "trajectory_results_after_run1.json",
    "trajectory_results_after_run2.json",
    "trajectory_results_after_run3.json",
]
# The run whose per-question detail is shown in the breakdown table -- the
# most recent, most fully-recovered post-mitigation run.
BREAKDOWN_FILE = "trajectory_results_after_run3.json"
# The run containing the traced right-answer-wrong-path example (q08).
GAP_EXAMPLE_FILE = "trajectory_results_after_run1.json"
GAP_EXAMPLE_ID = "q08"

METRIC_KEYS = [
    "tool_choice_accuracy",
    "argument_validity_rate",
    "step_efficiency",
    "cost_p50_usd",
    "cost_max_usd",
    "outcome_pass_rate",
    "trajectory_pass_rate",
    "outcome_minus_trajectory_gap",
]


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _load_many(filenames: list[str]) -> list[dict]:
    return [d for name in filenames if (d := _read_json(RESULTS_DIR / name)) is not None]


def _avg_summary(runs: list[dict]) -> dict:
    summaries = [r["summary"] for r in runs]
    if not summaries:
        return {}
    return {key: statistics.mean(s[key] for s in summaries) for key in METRIC_KEYS}


def load_comparison() -> dict:
    """Before/after averaged summary numbers, plus how many live runs and
    question-attempts each side is averaged over.
    """
    before_runs = _load_many(BEFORE_FILES)
    after_runs = _load_many(AFTER_FILES)
    return {
        "before": {
            "n_runs": len(before_runs),
            "n_questions": sum(r["summary"]["n"] for r in before_runs),
            "metrics": _avg_summary(before_runs),
        },
        "after": {
            "n_runs": len(after_runs),
            "n_questions": sum(r["summary"]["n"] for r in after_runs),
            "metrics": _avg_summary(after_runs),
        },
    }


def load_mode_regression() -> list[dict]:
    """One row per failure mode ever observed, with its count and rate
    before and after. Rate (not raw count) drives the verdict badge,
    because the before/after sample sizes differ (20 vs. 30 attempts) --
    comparing raw counts across different N would call a flat rate "worse".
    """
    before_runs = _load_many(BEFORE_FILES)
    after_runs = _load_many(AFTER_FILES)
    n_before = sum(r["summary"]["n"] for r in before_runs)
    n_after = sum(r["summary"]["n"] for r in after_runs)

    def counts(runs: list[dict]) -> dict:
        tally: dict[str, int] = {}
        for run in runs:
            for record in run["records"]:
                mode = record.get("failure_mode")
                if mode:
                    tally[mode] = tally.get(mode, 0) + 1
        return tally

    before_counts = counts(before_runs)
    after_counts = counts(after_runs)
    all_modes = ["hallucinated_tool", "api_error", "extra_steps", "missing_step", "wrong_target", "wrong_tool", "wrong_combination", "no_tool_call"]
    seen = [m for m in all_modes if m in before_counts or m in after_counts]
    # Catch any mode this eval produces that isn't in the fixed ordering above.
    seen += sorted((set(before_counts) | set(after_counts)) - set(seen))
    return [
        {
            "mode": mode,
            "before": before_counts.get(mode, 0),
            "after": after_counts.get(mode, 0),
            "before_rate": before_counts.get(mode, 0) / n_before if n_before else 0.0,
            "after_rate": after_counts.get(mode, 0) / n_after if n_after else 0.0,
        }
        for mode in seen
    ]


def load_breakdown() -> list[dict]:
    """Per-question detail table from one representative post-mitigation run."""
    data = _read_json(RESULTS_DIR / BREAKDOWN_FILE)
    if not data:
        return []
    return data["records"]


def load_gap_example() -> dict | None:
    data = _read_json(RESULTS_DIR / GAP_EXAMPLE_FILE)
    if not data:
        return None
    for record in data["records"]:
        if record["id"] == GAP_EXAMPLE_ID:
            return record
    return None


def load_cases() -> list[dict]:
    cases_path = Path(__file__).resolve().parent / "cases.json"
    return json.loads(cases_path.read_text()) if cases_path.exists() else []
