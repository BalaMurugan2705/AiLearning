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


def test_a4_does_not_count_a_version_named_only_inside_an_ascii_citation():
    """Pins the bug where a chunk id like `[chunk: v2:client:structural:2]`
    alone made A4 pass. The chunk id says where the answer's claim was
    retrieved from, not which version the answer's own prose describes --
    and nearly every answer carries a citation, so leaving it unstripped
    would make A4 pass almost everything."""
    answer = "The default retry backoff is 500 ms. [chunk: v2:client:structural:2]"
    assert assert_version_stated(answer, True)["status"] == FAIL


def test_a4_does_not_count_a_version_named_only_inside_a_full_width_citation():
    """Same bug, full-width bracket style (also seen in this project's traces)."""
    answer = "The default retry backoff is 500 ms. 【chunk: v3:client:structural:2】"
    assert assert_version_stated(answer, True)["status"] == FAIL


def test_a4_accepts_a_capitalised_v3_and_a_spelled_out_version_3():
    """LLM prose capitalises at sentence start and sometimes spells the word
    out -- a regex that only matches the terse lowercase form manufactures
    false FAILs on correct answers."""
    assert assert_version_stated("V3 uses cursors.", True)["status"] == PASS
    assert assert_version_stated("Version 3 uses cursors.", True)["status"] == PASS


def test_a4_still_passes_when_prose_names_a_version_alongside_a_citation():
    """Guards against over-stripping: the citation next to the sentence is
    noise, but a genuine version statement right beside it must still count."""
    answer = "In v3 the default is 2000 ms. [chunk: v3:client:structural:2]"
    result = assert_version_stated(answer, True)
    assert result["status"] == PASS
    assert "v3" in result["detail"]


def test_a1_skips_a_pycon_transcript_rather_than_failing_it():
    """Pins the bug where `(?:python|py)[^\\n]*` had no boundary after the
    tag, so "py" swallowed "con" from a ```pycon fence and sent a REPL
    transcript's `>>>` prompt through ast.parse -- a false FAIL on a
    correct answer."""
    answer = "```pycon\n>>> 1 + 1\n2\n```\n"
    assert assert_code_parses(answer)["status"] == SKIPPED


def test_a1_fails_an_unterminated_python_fence_naming_truncation():
    """max_tokens=2048 makes truncation mid-fence a live failure mode. An
    opening ```python with no closing fence is a broken sample, not "no
    code at all" -- it must FAIL, not SKIP, and the detail must say so."""
    result = assert_code_parses("```python\nx = 1\n")
    assert result["status"] == FAIL
    assert "truncat" in result["detail"].lower()
