"""THE one command: python -m eval.week6.run

Scores the frozen snapshot with the five deterministic assertions, folds in
whichever judge runs exist, and prints pass rate BY MODE. Never pooled into a
single headline: the average would hide a total regression on the
version-confusion mode while the clean mode carried the number.
"""
import argparse
import json
from pathlib import Path

from eval.spec import load_specs
from eval.week6 import report
from eval.week6.agreement import compare
from eval.week6.assertions import ASSERTION_IDS, FAIL, PASS, assertions_ok, run_assertions
from eval.week6.build_cases import MODES, load_cases
from eval.week6.judge import LABELS_PATH, run_path_for
from eval.week6.snapshot import load_snapshot

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
OUT_JSON = REPO / "eval" / "raw" / "week6.json"
OUT_MD = REPO / "results" / "week6-results.md"

# judge_v0 asked six questions; five became assertions and one stayed.
JUDGE_V0_CRITERIA = 6
JUDGED_CRITERIA = 1


def score_cases(snapshot: dict, cases: list[dict], specs: dict) -> list[dict]:
    case_by_id = {c["case_id"]: c for c in cases}
    rows = []
    for rec in snapshot["answers"]:
        case = case_by_id[rec["case_id"]]
        results = run_assertions(rec["raw_output"], case, specs)
        rows.append(
            {
                "case_id": rec["case_id"],
                "mode": rec["mode"],
                "assertions": results,
                "assertions_ok": assertions_ok(results),
            }
        )
    return rows


def mode_table(rows: list[dict], verdicts: list[dict] | None) -> dict:
    verdict_by_case = {v["case_id"]: v["verdict"] for v in (verdicts or [])}
    table: dict = {}

    for row in rows:
        bucket = table.setdefault(
            row["mode"],
            {
                "n": 0,
                "assertions_ok": 0,
                "judge_pass": 0 if verdicts else None,
                "overall": 0 if verdicts else None,
                "assertion_pass_counts": {aid: 0 for aid in ASSERTION_IDS},
                "assertion_fail_counts": {aid: 0 for aid in ASSERTION_IDS},
            },
        )
        bucket["n"] += 1
        if row["assertions_ok"]:
            bucket["assertions_ok"] += 1

        for result in row["assertions"]:
            # skipped increments neither counter: an assertion that did not run
            # is not a pass.
            if result["status"] == PASS:
                bucket["assertion_pass_counts"][result["id"]] += 1
            elif result["status"] == FAIL:
                bucket["assertion_fail_counts"][result["id"]] += 1

        if verdicts:
            judged_pass = verdict_by_case.get(row["case_id"]) == "PASS"
            if judged_pass:
                bucket["judge_pass"] += 1
            if judged_pass and row["assertions_ok"]:
                bucket["overall"] += 1

    return table


def build_report(snapshot, cases, specs, judge_runs: dict, labels: dict | None) -> dict:
    rows = score_cases(snapshot, cases, specs)
    modes = {rec["case_id"]: rec["mode"] for rec in snapshot["answers"]}

    agreements = {}
    for version, run in judge_runs.items():
        if labels is None:
            continue
        agreements[version] = compare(labels["labels"], run["verdicts"], modes)

    primary = judge_runs.get("v2") or judge_runs.get("v1")
    return {
        "n_cases": len(rows),
        "answers_sha256": snapshot["answers_sha256"],
        "assertion_count": len(ASSERTION_IDS),
        "judged_criteria_count": JUDGED_CRITERIA,
        "judge_v0_criteria_count": JUDGE_V0_CRITERIA,
        "by_mode": mode_table(rows, primary["verdicts"] if primary else None),
        "rows": rows,
        "judge_runs": {
            version: {
                "judge_prompt": run["judge_prompt"],
                "judge_model": run["judge_model"],
                "labels_commit": run["labels_commit"],
                "labels_sha256": run["labels_sha256"],
                "run_at": run["run_at"],
            }
            for version, run in judge_runs.items()
        },
        "agreement": agreements,
    }


def _print_mode_table(rep: dict) -> None:
    print(f"\n=== Pass rate by mode (n={rep['n_cases']}) ===")
    print(f"{'mode':<22}{'n':>3}{'assert':>9}{'judge':>8}{'overall':>10}")
    totals = {"n": 0, "assertions_ok": 0, "judge_pass": 0, "overall": 0}
    has_judge = any(b["judge_pass"] is not None for b in rep["by_mode"].values())

    for mode in MODES:
        bucket = rep["by_mode"].get(mode)
        if bucket is None:
            continue
        n = bucket["n"]
        a = bucket["assertions_ok"]
        j = bucket["judge_pass"]
        o = bucket["overall"]
        totals["n"] += n
        totals["assertions_ok"] += a
        if has_judge:
            totals["judge_pass"] += j or 0
            totals["overall"] += o or 0
        j_txt = f"{j}/{n}" if j is not None else "-"
        o_txt = f"{o}/{n} {o / n:.0%}" if o is not None else "-"
        print(f"{mode:<22}{n:>3}{f'{a}/{n}':>9}{j_txt:>8}{o_txt:>10}")

    print("-" * 52)
    n = totals["n"]
    o_txt = f"{totals['overall']}/{n} {totals['overall'] / n:.0%}" if has_judge else "-"
    j_txt = f"{totals['judge_pass']}/{n}" if has_judge else "-"
    print(f"{'TOTAL':<22}{n:>3}{f'{totals["assertions_ok"]}/{n}':>9}{j_txt:>8}{o_txt:>10}")

    print("\n=== Assertions vs judged criteria ===")
    print(
        f"deterministic assertions: {rep['assertion_count']}    "
        f"judged criteria: {rep['judged_criteria_count']}    "
        f"(judge_v0 had {rep['judge_v0_criteria_count']})"
    )

    if rep["agreement"]:
        print("\n=== Judge agreement with the 25 human labels ===")
        for version in ("v1", "v2"):
            agr = rep["agreement"].get(version)
            if agr is None:
                continue
            name = "agreement_before" if version == "v1" else "agreement_after "
            commit = rep["judge_runs"][version]["labels_commit"][:12]
            print(
                f"{name} (judge_{version}): {agr['agreement']:.0%}  "
                f"kappa {agr['kappa']:.2f}  "
                f"matches {agr['matches']}/{agr['n']}  "
                f"[labels commit {commit}]"
            )
        print("\nkappa is reported next to the percentage because on a skewed label")
        print("set a judge that always answers PASS scores high agreement while")
        print("never reading anything.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-judge", action="store_true", help="assertions only, no API key needed")
    args = parser.parse_args()

    snapshot = load_snapshot()
    cases = load_cases()
    specs = load_specs()

    judge_runs = {}
    if not args.no_judge:
        for version in ("v1", "v2"):
            path = run_path_for(version)
            if path.exists():
                judge_runs[version] = json.loads(path.read_text(encoding="utf-8"))

    labels = None
    if LABELS_PATH.exists():
        labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))

    rep = build_report(snapshot, cases, specs, judge_runs, labels)
    _print_mode_table(rep)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(report.render(rep), encoding="utf-8")
    print(f"\nwrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
