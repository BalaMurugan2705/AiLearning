"""Race agent vs workflow over one golden-set difficulty level (easy,
medium, or hard) instead of the assignment's curated 10 -- run as:

    python -m eval.week7.run_golden_race easy
    python -m eval.week7.run_golden_race medium
    python -m eval.week7.run_golden_race hard

Writes results/week7/race_<level>.csv and race_details_<level>.json,
reusing the same run_system()/write_race_results() the main 10-question
race uses so both races are graded identically.
"""
import sys

from agent.loop import run_agent
from agent.workflow import run_workflow
from eval.week7.golden_questions import load_golden_set
from eval.week7.run_race import RESULTS_DIR, run_system, write_race_results


def run_level(level: str) -> None:
    questions = load_golden_set(level)
    agent_records = run_system(run_agent, questions)
    workflow_records = run_system(run_workflow, questions)
    write_race_results(
        RESULTS_DIR / f"race_{level}.csv",
        RESULTS_DIR / f"race_details_{level}.json",
        agent_records,
        workflow_records,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("easy", "medium", "hard"):
        print("Usage: python -m eval.week7.run_golden_race {easy|medium|hard}")
        sys.exit(1)
    run_level(sys.argv[1])
