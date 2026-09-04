"""Human-vs-judge agreement.

Reports raw agreement (the two numbers the task asks for) alongside the
confusion matrix and Cohen's kappa. Kappa is not decoration: on a skewed label
set, a judge that answers PASS unconditionally scores high raw agreement while
never reading anything, and only kappa makes that visible.
"""


def cohens_kappa(tp: int, fp: int, fn: int, tn: int) -> float:
    """Agreement corrected for the agreement two coin-flips would reach."""
    n = tp + fp + fn + tn
    if n == 0:
        return 0.0

    observed = (tp + tn) / n
    human_pass = (tp + fn) / n
    judge_pass = (tp + fp) / n
    expected = human_pass * judge_pass + (1 - human_pass) * (1 - judge_pass)

    if expected >= 1.0:
        return 0.0
    return (observed - expected) / (1 - expected)


def compare(labels: list[dict], verdicts: list[dict], modes: dict[str, str]) -> dict:
    label_by_case = {row["case_id"]: bool(row["label"]) for row in labels}
    verdict_by_case = {row["case_id"]: row["verdict"] for row in verdicts}

    if set(label_by_case) != set(verdict_by_case):
        missing = set(label_by_case) ^ set(verdict_by_case)
        raise ValueError(f"case_id mismatch between labels and verdicts: {sorted(missing)}")

    tp = fp = fn = tn = 0
    unparsed = 0
    matches = 0
    disagreements = []
    by_mode: dict[str, dict] = {}

    for case_id in sorted(label_by_case):
        human = label_by_case[case_id]
        judge = verdict_by_case[case_id]
        mode = modes.get(case_id, "unknown")

        # An unparseable verdict is a disagreement, never a free pass -- the
        # judge failed to answer the question it was asked.
        if judge not in ("PASS", "FAIL"):
            unparsed += 1
            agreed = False
        else:
            judge_pass = judge == "PASS"
            agreed = judge_pass == human
            if human and judge_pass:
                tp += 1
            elif human and not judge_pass:
                fn += 1
            elif not human and judge_pass:
                fp += 1
            else:
                tn += 1

        bucket = by_mode.setdefault(mode, {"n": 0, "matches": 0, "agreement": 0.0})
        bucket["n"] += 1
        if agreed:
            matches += 1
            bucket["matches"] += 1
        else:
            disagreements.append(
                {"case_id": case_id, "mode": mode, "human": human, "judge": judge}
            )

    for bucket in by_mode.values():
        bucket["agreement"] = bucket["matches"] / bucket["n"] if bucket["n"] else 0.0

    n = len(label_by_case)
    return {
        "n": n,
        "matches": matches,
        "agreement": matches / n if n else 0.0,
        "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        "kappa": cohens_kappa(tp, fp, fn, tn),
        "human_pass_rate": sum(label_by_case.values()) / n if n else 0.0,
        "unparsed": unparsed,
        "disagreements": disagreements,
        "by_mode": dict(sorted(by_mode.items())),
    }
