"""Blind labeling: 25 answers, one binary criterion, no judge output anywhere.

Two properties make this blind rather than nominally blind. First, this module
never reads a judge run's contents -- there is no code path by which the
judge's opinion could reach the screen. Second, it refuses to run at all once
a judge run file exists, unless forced, and a forced run stamps
"blind": false into its own output.

The criterion shown here is read out of judge_v1.txt rather than duplicated,
so the human and the judge cannot end up answering slightly different
questions. Seeing the criterion is correct and necessary; seeing the judge's
answers is not.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eval.week6.criterion import JUDGE_V1_PATH, read_criterion, sha256_text
from eval.week6.judge import LABELS_PATH, run_path_for
from eval.week6.snapshot import load_snapshot


class BlindnessError(Exception):
    """Raised when labeling would no longer be blind."""


def ensure_blind(run_paths: list[Path], force: bool) -> bool:
    """Return whether this session is blind, refusing if it is not and not forced."""
    existing = [p for p in run_paths if p.exists()]
    if not existing:
        return True
    if force:
        return False
    raise BlindnessError(
        f"The judge has already been run ({', '.join(p.name for p in existing)}). "
        "Labeling now would not be blind -- you would be agreeing with an opinion "
        "you have already seen. Pass --force-relabel only if you accept that the "
        "output will be marked blind=false."
    )


def render_case(answer_rec: dict, index: int, total: int) -> str:
    """One case, as the labeler sees it.

    Deliberately omits the mode tag: telling the labeler this case was filed
    under "version-ambiguity" would tell them what to look for.
    """
    chunks = "\n".join(
        f"  [{c.get('chunk_id')}] {c.get('source_file')}: {' '.join((c.get('text') or '').split())[:160]}"
        for c in answer_rec["retrieved"]
    ) or "  (nothing retrieved)"
    return (
        f"\n{'=' * 78}\n"
        f"CASE {index}/{total}  {answer_rec['case_id']}\n"
        f"{'=' * 78}\n"
        f"QUESTION:\n  {answer_rec['question']}\n\n"
        f"RETRIEVED:\n{chunks}\n\n"
        f"ANSWER:\n{answer_rec['raw_output']}\n"
        f"{'-' * 78}\n"
    )


def build_labels_file(
    criterion: str, answers_sha256: str, rows: list[dict], blind: bool
) -> dict:
    return {
        "criterion_text": criterion,
        "criterion_sha256": sha256_text(criterion),
        "answers_sha256": answers_sha256,
        "blind": blind,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "labels": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labeler", required=True, help="who is labeling, recorded in the file")
    parser.add_argument("--force-relabel", action="store_true")
    args = parser.parse_args()

    blind = ensure_blind([run_path_for("v1"), run_path_for("v2")], args.force_relabel)

    snapshot = load_snapshot()
    criterion = read_criterion(JUDGE_V1_PATH)
    answers = snapshot["answers"]

    print("\nYou are labeling on ONE binary criterion:\n")
    print(f"  {criterion}\n")
    print("  y = yes (PASS)   n = no (FAIL)   ? = show the case again   q = save and quit\n")
    print("Answer only that question. Code syntax, symbol spelling, endpoint")
    print("existence, version-label presence and citation formatting are all")
    print("checked by code -- ignore them here.\n")

    rows = []
    for index, rec in enumerate(answers, start=1):
        print(render_case(rec, index, len(answers)))
        while True:
            choice = input("  label [y/n/?/q]: ").strip().lower()
            if choice == "?":
                print(render_case(rec, index, len(answers)))
                continue
            if choice == "q":
                print(f"\nStopping early with {len(rows)}/{len(answers)} labeled.")
                _write(args.labeler, criterion, snapshot, rows, blind)
                return
            if choice in ("y", "n"):
                note = input("  note (optional): ").strip()
                rows.append(
                    {"case_id": rec["case_id"], "label": choice == "y", "note": note}
                )
                break
            print("  please answer y, n, ? or q")

    _write(args.labeler, criterion, snapshot, rows, blind)


def _write(labeler: str, criterion: str, snapshot: dict, rows: list[dict], blind: bool) -> None:
    payload = build_labels_file(criterion, snapshot["answers_sha256"], rows, blind)
    payload["labeler"] = labeler
    LABELS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    passes = sum(1 for r in rows if r["label"])
    print(f"\nwrote {LABELS_PATH}")
    print(f"labels: {len(rows)}  pass: {passes}  fail: {len(rows) - passes}  blind: {blind}")
    print("\nNEXT: commit this file ON ITS OWN before running the judge:")
    print("  git add eval/week6/labels_25.json")
    print('  git commit -m "week6: 25 blind labels (pre-judge)"')


if __name__ == "__main__":
    main()
