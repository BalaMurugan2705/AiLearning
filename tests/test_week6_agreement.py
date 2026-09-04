"""Agreement between the human labels and the judge.

Raw agreement alone is not enough to trust. With a skewed label set a judge
that answers PASS unconditionally scores high while never reading anything --
the same "one pooled number hides it" failure the task warns about, one level
up. Cohen's kappa is reported next to the percentage so that judge is visible.
"""
from eval.week6.agreement import cohens_kappa, compare

MODES = {"W6-01": "clean", "W6-02": "clean", "W6-03": "version-ambiguity", "W6-04": "version-ambiguity"}


def _labels(*values):
    return [{"case_id": f"W6-0{i+1}", "label": v} for i, v in enumerate(values)]


def _verdicts(*values):
    return [{"case_id": f"W6-0{i+1}", "verdict": v, "reason": "r"} for i, v in enumerate(values)]


def test_perfect_agreement_is_one_hundred_percent():
    result = compare(_labels(True, False), _verdicts("PASS", "FAIL"), MODES)
    assert result["matches"] == 2
    assert result["agreement"] == 1.0


def test_total_disagreement_is_zero_percent():
    result = compare(_labels(True, False), _verdicts("FAIL", "PASS"), MODES)
    assert result["agreement"] == 0.0


def test_confusion_matrix_uses_the_human_label_as_reference():
    result = compare(
        _labels(True, True, False, False), _verdicts("PASS", "FAIL", "PASS", "FAIL"), MODES
    )
    assert result["confusion"] == {"tp": 1, "fn": 1, "fp": 1, "tn": 1}


def test_disagreements_name_the_case_the_mode_and_both_opinions():
    result = compare(_labels(True, True), _verdicts("PASS", "FAIL"), MODES)
    assert len(result["disagreements"]) == 1
    d = result["disagreements"][0]
    assert d["case_id"] == "W6-02"
    assert d["human"] is True
    assert d["judge"] == "FAIL"
    assert d["mode"] == "clean"


def test_agreement_is_broken_out_per_mode():
    result = compare(
        _labels(True, True, True, True), _verdicts("PASS", "PASS", "FAIL", "FAIL"), MODES
    )
    assert result["by_mode"]["clean"]["agreement"] == 1.0
    assert result["by_mode"]["version-ambiguity"]["agreement"] == 0.0


def test_an_unparsed_verdict_counts_as_a_disagreement_not_a_free_pass():
    result = compare(_labels(True), _verdicts("UNPARSED"), MODES)
    assert result["matches"] == 0
    assert result["unparsed"] == 1


def test_kappa_is_one_for_perfect_agreement():
    assert cohens_kappa(tp=10, fp=0, fn=0, tn=10) == 1.0


def test_kappa_exposes_a_judge_that_always_says_pass():
    """22 of 25 labels are PASS, so a judge that never reads anything and
    always says PASS scores 88% raw agreement. Kappa says 0."""
    result = compare(
        _labels(*([True] * 22 + [False] * 3)), _verdicts(*(["PASS"] * 25)), {}
    )
    assert round(result["agreement"], 2) == 0.88
    assert round(result["kappa"], 3) == 0.0


def test_kappa_is_zero_when_expected_agreement_is_total():
    assert cohens_kappa(tp=25, fp=0, fn=0, tn=0) == 0.0


def test_compare_requires_the_same_case_ids_on_both_sides():
    import pytest

    with pytest.raises(ValueError, match="case_id"):
        compare(_labels(True), _verdicts("PASS", "PASS"), MODES)
