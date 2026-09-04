"""The one command's arithmetic.

Pass rate is reported per mode and never pooled: an average will happily hide
a total regression on the version-confusion mode while the clean mode carries
the number.
"""
from eval.week6.run import mode_table, score_cases

SPECS = {
    "symbols": {"retry_backoff_ms": {"kind": "parameter", "versions": ["v3"], "sources": []}},
    "openapi": {"paths": {"/v3/auth/token": {"post": {}}}},
    "deprecations": [],
}

CASES = [
    {"case_id": "W6-01", "mode": "clean", "version_sensitive": True},
    {"case_id": "W6-02", "mode": "version-ambiguity", "version_sensitive": True},
]

SNAPSHOT = {
    "answers": [
        {"case_id": "W6-01", "mode": "clean", "raw_output": "In v3, `retry_backoff_ms` is 2000 ms."},
        {"case_id": "W6-02", "mode": "version-ambiguity", "raw_output": "It is 500 ms."},
    ]
}


def test_score_cases_runs_all_five_assertions_per_case():
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    assert len(rows) == 2
    assert len(rows[0]["assertions"]) == 5


def test_a_case_with_a_failing_assertion_is_not_assertions_ok():
    rows = {r["case_id"]: r for r in score_cases(SNAPSHOT, CASES, SPECS)}
    assert rows["W6-01"]["assertions_ok"] is True
    assert rows["W6-02"]["assertions_ok"] is False, "no v2/v3 named, so A4 fails"


def test_mode_table_reports_each_mode_separately():
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    verdicts = [
        {"case_id": "W6-01", "verdict": "PASS", "reason": ""},
        {"case_id": "W6-02", "verdict": "PASS", "reason": ""},
    ]
    table = mode_table(rows, verdicts)
    assert table["clean"]["overall"] == 1
    assert table["version-ambiguity"]["overall"] == 0, "assertion failure blocks the pass"


def test_overall_pass_needs_both_the_assertions_and_the_judge():
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    verdicts = [
        {"case_id": "W6-01", "verdict": "FAIL", "reason": ""},
        {"case_id": "W6-02", "verdict": "PASS", "reason": ""},
    ]
    table = mode_table(rows, verdicts)
    assert table["clean"]["assertions_ok"] == 1
    assert table["clean"]["judge_pass"] == 0
    assert table["clean"]["overall"] == 0


def test_mode_table_works_with_no_judge_run_at_all():
    """--no-judge must still produce the assertion half of the table so the
    deterministic checks can be run without an API key."""
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    table = mode_table(rows, verdicts=None)
    assert table["clean"]["assertions_ok"] == 1
    assert table["clean"]["judge_pass"] is None
    assert table["clean"]["overall"] is None


def test_skipped_assertions_never_count_as_passes():
    """A3 applies to almost no case. If skipped counted as pass it would
    donate free passes and manufacture a pass rate out of nothing."""
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    a3 = next(a for a in rows[0]["assertions"] if a["id"].startswith("A3"))
    assert a3["status"] == "skipped"
    counts = mode_table(rows, verdicts=None)["clean"]
    assert counts["assertion_pass_counts"]["A3_endpoints_exist"] == 0
