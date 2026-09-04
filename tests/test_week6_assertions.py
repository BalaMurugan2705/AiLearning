"""The five deterministic assertions moved out of judge_v0.

Each one gets a passing case, a failing case, and a not-applicable case. The
not-applicable cases matter as much as the others: an assertion that returns
"pass" when it did not actually run would let A3 alone donate ~20 free passes
to the 25-case table and manufacture a pass rate out of nothing.
"""
from eval.week6.assertions import (
    A1,
    A4,
    ASSERTION_IDS,
    FAIL,
    PASS,
    SKIPPED,
    assert_code_parses,
    assert_deprecation_has_migration_note,
    assert_endpoints_exist,
    assert_symbols_exist,
    assert_version_stated,
    assertions_ok,
    run_assertions,
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


SYMBOLS = {
    "RELAY_429": {"kind": "error_code", "versions": ["v2", "v3"], "sources": []},
    "retry_backoff_ms": {"kind": "parameter", "versions": ["v2", "v3"], "sources": []},
    "Client.send()": {"kind": "method", "versions": ["v2", "v3"], "sources": []},
    "RelayTimeout": {"kind": "class", "versions": ["v3"], "sources": []},
}

OPENAPI = {"paths": {"/v3/auth/token": {"post": {}}}}

DEPRECATIONS = [
    {
        "id": "offset-pagination",
        "label": "offset pagination",
        "match": r"\b(page_offset|offset pagination)\b",
        "replacement": "next_cursor",
        "migration_signals": ["next_cursor", "removed in v3"],
        "source": "migrating-to-v3.md",
    }
]


def test_a2_passes_an_answer_using_only_real_symbols():
    answer = "`Client.send()` retries on `RELAY_429`; tune `retry_backoff_ms`."
    assert assert_symbols_exist(answer, SYMBOLS)["status"] == PASS


def test_a2_fails_a_fabricated_error_code():
    result = assert_symbols_exist("Handle `RELAY_777` on failure.", SYMBOLS)
    assert result["status"] == FAIL
    assert "RELAY_777" in result["detail"]


def test_a2_fails_a_fabricated_parameter():
    result = assert_symbols_exist("Set `retry_delay_ms` to 2000.", SYMBOLS)
    assert result["status"] == FAIL
    assert "retry_delay_ms" in result["detail"]


def test_a2_fails_a_fabricated_qualified_method():
    result = assert_symbols_exist("Call `Client.sendBatch()` instead.", SYMBOLS)
    assert result["status"] == FAIL


def test_a2_never_examines_bare_prose_words_or_builtins():
    """The corpus backticks `str`, `int`, `None`, `message`. Checking those
    against the table would fail on ordinary English, so the shape rules
    exclude every single-word token.

    A real symbol is included so this asserts PASS rather than SKIPPED --
    otherwise the test would pass simply because nothing was examined, and
    would keep passing if the noise-filtering broke.
    """
    answer = "`RELAY_429` is retried; the `message` is a `str`, `metadata` is `None`, `id` an `int`."
    assert assert_symbols_exist(answer, SYMBOLS)["status"] == PASS


def test_a2_ignores_local_variables_inside_code_fences():
    answer = "```python\nmy_client = Client(api_key='k')\nraw_payload = {}\n```\n"
    assert assert_symbols_exist(answer, SYMBOLS)["status"] == SKIPPED


def test_a2_is_skipped_when_no_sdk_shaped_token_appears():
    assert assert_symbols_exist("The docs do not say.", SYMBOLS)["status"] == SKIPPED


def test_a3_passes_the_one_documented_path():
    answer = "Exchange the key at `POST /v3/auth/token`."
    assert assert_endpoints_exist(answer, OPENAPI)["status"] == PASS


def test_a3_fails_a_hallucinated_endpoint():
    result = assert_endpoints_exist("Refresh via `POST /v3/tokens/refresh`.", OPENAPI)
    assert result["status"] == FAIL
    assert "/v3/tokens/refresh" in result["detail"]


def test_a3_is_skipped_when_the_answer_mentions_no_path():
    assert assert_endpoints_exist("The SDK handles it.", OPENAPI)["status"] == SKIPPED


def test_a3_strips_trailing_punctuation_from_a_path():
    assert assert_endpoints_exist("Call /v3/auth/token.", OPENAPI)["status"] == PASS


def test_a5_passes_a_deprecated_mention_that_carries_its_migration_note():
    answer = "v2 used offset pagination; in v3 thread `next_cursor` instead."
    assert assert_deprecation_has_migration_note(answer, DEPRECATIONS)["status"] == PASS


def test_a5_fails_a_deprecated_recommendation_with_no_note():
    answer = "Use offset pagination to page through results."
    result = assert_deprecation_has_migration_note(answer, DEPRECATIONS)
    assert result["status"] == FAIL
    assert "offset-pagination" in result["detail"]


def test_a5_requires_the_note_in_the_same_paragraph():
    """A migration note three paragraphs away does not help a reader who
    copies the code block next to the deprecated mention."""
    answer = "Use offset pagination to page.\n\nUnrelated.\n\nv3 uses `next_cursor`."
    assert assert_deprecation_has_migration_note(answer, DEPRECATIONS)["status"] == FAIL


def test_a5_falls_back_to_a_character_window_with_no_blank_lines():
    answer = "Use offset pagination, though v3 replaced it with next_cursor."
    assert assert_deprecation_has_migration_note(answer, DEPRECATIONS)["status"] == PASS


def test_a5_is_skipped_when_no_deprecated_thing_is_mentioned():
    answer = "The default retry backoff is 2000 ms in v3."
    assert assert_deprecation_has_migration_note(answer, DEPRECATIONS)["status"] == SKIPPED


def test_run_assertions_returns_all_five_in_order():
    case = {"version_sensitive": True}
    specs = {"symbols": SYMBOLS, "openapi": OPENAPI, "deprecations": DEPRECATIONS}
    results = run_assertions("In v3 the default is 2000 ms.", case, specs)
    assert [r["id"] for r in results] == list(ASSERTION_IDS)


def test_assertions_ok_treats_skipped_as_not_a_failure():
    results = [{"id": A1, "status": SKIPPED, "detail": ""}, {"id": A4, "status": PASS, "detail": ""}]
    assert assertions_ok(results) is True


def test_assertions_ok_is_false_when_anything_failed():
    results = [{"id": A1, "status": PASS, "detail": ""}, {"id": A4, "status": FAIL, "detail": ""}]
    assert assertions_ok(results) is False
