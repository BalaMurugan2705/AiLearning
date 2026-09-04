"""judge_v0 -> judge_v1 is the assertion/judge split, as a diff.

v0 asks six questions, five of which a program can settle exactly. v1 is v0
with those five deleted. The test asserts the deletion actually happened,
because a "split" that leaves the criteria in the prompt is cosmetic -- the
judge would go on silently re-litigating what the assertions already decided.
"""
from eval.week6.criterion import (
    JUDGE_V0_PATH,
    JUDGE_V1_PATH,
    read_criterion,
    sha256_text,
)

# Wording that would show a moved criterion is still being judged.
ASSERTED_CRITERIA_MARKERS = [
    "syntactically valid",
    "exists in the SDK",
    "exists in the API spec",
    "states which SDK version",
    "without a migration note",
]


def test_v0_contains_all_six_criteria():
    text = JUDGE_V0_PATH.read_text(encoding="utf-8")
    for marker in ASSERTED_CRITERIA_MARKERS:
        assert marker in text, f"v0 should still ask about: {marker}"


def test_v1_has_deleted_every_asserted_criterion():
    text = JUDGE_V1_PATH.read_text(encoding="utf-8").lower()
    for marker in ASSERTED_CRITERIA_MARKERS:
        assert marker.lower() not in text, f"v1 still judges an asserted criterion: {marker}"


def test_v1_tells_the_judge_not_to_re_judge_the_asserted_things():
    text = JUDGE_V1_PATH.read_text(encoding="utf-8").lower()
    assert "checked separately" in text or "checked deterministically" in text


def test_v1_declares_exactly_one_criterion():
    text = JUDGE_V1_PATH.read_text(encoding="utf-8")
    assert text.count("CRITERION:") == 1


def test_v1_demands_the_strict_output_contract():
    text = JUDGE_V1_PATH.read_text(encoding="utf-8")
    assert "VERDICT:" in text and "REASON:" in text
    assert "1-10" not in text and "1 to 10" not in text, "must be binary, not a scale"


def test_read_criterion_returns_the_single_criterion_line():
    criterion = read_criterion(JUDGE_V1_PATH)
    assert criterion.startswith("Would a developer")
    assert "CRITERION:" not in criterion


def test_sha256_text_is_stable():
    assert sha256_text("abc") == sha256_text("abc")
    assert sha256_text("abc") != sha256_text("abd")
