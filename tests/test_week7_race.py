from types import SimpleNamespace

from eval.week7 import run_race
from eval.week7.run_race import aggregate, grade, grade_entry, grade_refusal


def test_grade_is_case_insensitive_substring_match():
    assert grade("Use ASSIGNEES instead.", "assignees") is True
    assert grade("Use assignee instead.", "assignees") is False


def test_grade_handles_budget_terminated_run():
    assert grade(None, "assignees") is False


def test_grade_ignores_smart_typography_the_model_actually_produces():
    # Real Groq output for these two questions used a narrow no-break space
    # ("400 KB") and a non-breaking hyphen ("pre‑armed") -- both
    # answers were factually correct but failed a naive ASCII substring
    # check until grade() started normalizing typographic variants.
    assert grade("accepts content up to 400 KB in size", "400 KB") is True
    assert grade("auto-merge may be pre‑armed on a draft", "pre-armed") is True


def test_aggregate_computes_all_four_numbers():
    records = [
        {"passed": True, "wall_seconds": 1.0, "total_tokens": 100, "total_cost_usd": 0.01},
        {"passed": True, "wall_seconds": 2.0, "total_tokens": 200, "total_cost_usd": 0.02},
        {"passed": False, "wall_seconds": 3.0, "total_tokens": 300, "total_cost_usd": 0.03},
        {"passed": True, "wall_seconds": 4.0, "total_tokens": 400, "total_cost_usd": 0.04},
    ]
    result = aggregate(records)
    assert result["pass_rate"] == 0.75
    assert result["p50_latency_seconds"] == 2.5
    assert result["total_tokens"] == 1000
    assert round(result["cost_per_question_usd"], 4) == round(0.10 / 4, 4)


def test_aggregate_empty_records_does_not_crash():
    result = aggregate([])
    assert result["pass_rate"] == 0.0


def test_grade_refusal_recognizes_an_honest_not_in_the_docs_answer():
    assert grade_refusal("Information not provided in context.") is True
    assert grade_refusal("The rate limit is 5000 requests per hour.") is False


def test_grade_refusal_none_answer_is_not_a_pass():
    assert grade_refusal(None) is False


def test_grade_refusal_recognizes_real_phrasings_seen_in_live_answers():
    # Real Groq output for negative-case golden-set questions: neither of
    # these matched the original keyword list ("does not contain", "don't
    # know") until it was widened after seeing actual model wording.
    assert grade_refusal("The documentation excerpts do not contain information about X.") is True
    assert grade_refusal("I'm sorry, but I don't have the information needed to answer that.") is True
    assert grade_refusal("The documentation does not mention any such flag.") is True


def test_grade_entry_dispatches_on_is_negative_case():
    negative_entry = {"is_negative_case": True}
    assert grade_entry("Not covered in the documentation.", negative_entry) is True
    assert grade_entry("The answer is 42.", negative_entry) is False

    positive_entry = {"is_negative_case": False, "expected_fragment": "assignees"}
    assert grade_entry("Use assignees instead.", positive_entry) is True


def test_grade_entry_treats_missing_is_negative_case_as_positive():
    # eval/week7/questions.json entries never set is_negative_case at all.
    entry = {"expected_fragment": "assignees"}
    assert grade_entry("Use assignees instead.", entry) is True


def test_grade_entry_accepts_any_one_of_a_list_of_fragments():
    # A real answer paraphrased "unconditionally" as "regardless of
    # visibility" -- both are correct, so either should pass.
    entry = {"expected_fragment": ["unconditionally", "regardless of"]}
    assert grade_entry("It defaults to true regardless of visibility.", entry) is True
    assert grade_entry("It is set unconditionally to true.", entry) is True
    assert grade_entry("It depends on the repo type.", entry) is False


def test_run_system_continues_after_one_question_raises():
    # Real Groq behavior: it occasionally rejects a response outright with
    # "output_parse_failed" when the model emits raw reasoning text. That
    # used to crash the whole batch and lose every already-completed
    # result; now it's recorded as one failed record and the run continues.
    def flaky_run(question):
        if question == "boom":
            raise RuntimeError("output_parse_failed")
        return SimpleNamespace(
            answer="ok",
            terminated_by_budget=False,
            budget_reason=None,
            wall_seconds=0.1,
            total_tokens=10,
            total_cost_usd=0.0,
        )

    questions = [
        {"id": "a", "question": "boom", "needs_chain": False, "expected_fragment": "x"},
        {"id": "b", "question": "fine", "needs_chain": False, "expected_fragment": "ok"},
    ]
    records = run_race.run_system(flaky_run, questions)

    assert len(records) == 2
    assert records[0]["passed"] is False
    assert records[0]["answer"] is None
    assert "error" in records[0]["budget_reason"]
    assert records[1]["passed"] is True
