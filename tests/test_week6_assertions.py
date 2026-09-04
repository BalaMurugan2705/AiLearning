"""The five deterministic assertions moved out of judge_v0.

Each one gets a passing case, a failing case, and a not-applicable case. The
not-applicable cases matter as much as the others: an assertion that returns
"pass" when it did not actually run would let A3 alone donate ~20 free passes
to the 25-case table and manufacture a pass rate out of nothing.
"""
from eval.week6.assertions import (
    FAIL,
    PASS,
    SKIPPED,
    assert_code_parses,
    assert_version_stated,
)


def test_a1_passes_a_valid_python_fence():
    answer = "Use this:\n\n```python\nclient.send(message='x', channel='a/b/c')\n```\n"
    assert assert_code_parses(answer)["status"] == PASS


def test_a1_fails_a_fence_that_does_not_parse():
    answer = "```python\nclient.send(message='x',\n```\n"
    result = assert_code_parses(answer)
    assert result["status"] == FAIL
    assert "fence 0" in result["detail"]


def test_a1_is_skipped_when_the_answer_has_no_python_fence():
    result = assert_code_parses("The default is 2000 ms. [chunk: v3:client:structural:2]")
    assert result["status"] == SKIPPED, "no fence is not the same as a valid fence"


def test_a1_checks_every_fence_not_just_the_first():
    answer = "```python\nx = 1\n```\n\ntext\n\n```python\ndef broken(\n```\n"
    assert assert_code_parses(answer)["status"] == FAIL


def test_a1_tolerates_an_indented_fence():
    answer = "```python\n    receipt = client.send(message='x')\n```\n"
    assert assert_code_parses(answer)["status"] == PASS


def test_a4_passes_when_the_answer_names_a_version():
    result = assert_version_stated("In v3 the default is 2000 ms.", True)
    assert result["status"] == PASS
    assert "v3" in result["detail"]


def test_a4_fails_when_a_version_sensitive_answer_names_no_version():
    result = assert_version_stated("The default retry backoff is 2000 ms.", True)
    assert result["status"] == FAIL


def test_a4_is_skipped_for_a_case_that_is_not_version_sensitive():
    assert assert_version_stated("Anything.", False)["status"] == SKIPPED


def test_a4_does_not_judge_whether_the_version_is_correct():
    """Stated-ness is deterministic; correctness is the judge's half. An answer
    that confidently names the WRONG version still passes A4 -- that split is
    the whole point of the assertion/judge seam."""
    assert assert_version_stated("In v2 the default is 2000 ms.", True)["status"] == PASS
