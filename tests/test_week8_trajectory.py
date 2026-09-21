from eval.week8.trajectory_eval import (
    argument_is_valid,
    classify_failure_mode,
    extract_tool_calls,
    find_gap_examples,
    mode_counts,
    summarize,
    tool_choice_accuracy,
    trajectory_passes,
)

CASE = {
    "id": "q04",
    "expected_fragment": "assignees",
    "accepted_tool_sequences": [
        ["check_deprecation"],
        ["check_deprecation", "get_openapi_spec"],
        ["get_openapi_spec", "check_deprecation"],
    ],
    "min_steps": 1,
    "relevant_endpoint": "create_issue",
    "relevant_api_version": "2025-06-01",
}


def _call(name, **arguments):
    return {"name": name, "arguments": arguments}


def test_extract_tool_calls_reads_arguments_in_order_from_transcript():
    transcript = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "1", "type": "function", "function": {"name": "search_docs", "arguments": '{"query": "x"}'}},
                {"id": "2", "type": "function", "function": {"name": "check_deprecation", "arguments": '{"endpoint": "create_issue", "api_version": "2025-06-01"}'}},
            ],
        },
        {"role": "tool", "name": "search_docs", "content": "..."},
    ]
    calls = extract_tool_calls(transcript)
    assert calls == [
        {"name": "search_docs", "arguments": {"query": "x"}},
        {"name": "check_deprecation", "arguments": {"endpoint": "create_issue", "api_version": "2025-06-01"}},
    ]


def test_trajectory_passes_on_accepted_sequence_with_correct_target():
    calls = [_call("check_deprecation", endpoint="create_issue", api_version="2025-06-01")]
    assert trajectory_passes(CASE, calls) is True


def test_trajectory_fails_on_right_tool_wrong_endpoint():
    # This is the "recited from memory" shape: right tool family, but it
    # checked the wrong endpoint, so it did not actually verify this answer.
    calls = [_call("check_deprecation", endpoint="create_release", api_version="2025-06-01")]
    assert trajectory_passes(CASE, calls) is False
    assert classify_failure_mode(CASE, calls) == "wrong_target"


def test_trajectory_passes_when_both_versions_are_legitimately_compared():
    # A "chain" case whose accepted sequence checks both API versions of
    # the same endpoint: the second call's api_version necessarily differs
    # from relevant_api_version, and that must not count as a miss.
    chain_case = {
        "accepted_tool_sequences": [["get_openapi_spec", "get_openapi_spec"]],
        "min_steps": 1,
        "relevant_endpoint": "render_markdown",
        "relevant_api_version": "2025-06-01",
    }
    calls = [
        _call("get_openapi_spec", endpoint="render_markdown", api_version="2022-11-28"),
        _call("get_openapi_spec", endpoint="render_markdown", api_version="2025-06-01"),
    ]
    assert trajectory_passes(chain_case, calls) is True
    assert classify_failure_mode(chain_case, calls) is None


def test_trajectory_fails_with_no_tool_calls_at_all():
    assert trajectory_passes(CASE, []) is False
    assert classify_failure_mode(CASE, []) == "no_tool_call"


def test_classify_wrong_tool_when_none_of_the_calls_are_in_the_allowed_set():
    calls = [_call("search_docs", query="issue assignee")]
    assert classify_failure_mode(CASE, calls) == "wrong_tool"


def test_classify_extra_steps_when_sequence_not_accepted_and_longer_than_min():
    calls = [
        _call("check_deprecation", endpoint="create_issue", api_version="2025-06-01"),
        _call("check_deprecation", endpoint="create_issue", api_version="2025-06-01"),
    ]
    # Sequence ["check_deprecation", "check_deprecation"] is not an accepted
    # sequence for this case, all tools used are legitimate, and it's longer
    # than min_steps -- a redundant repeat call.
    assert classify_failure_mode(CASE, calls) == "extra_steps"


def test_passed_case_has_no_failure_mode():
    calls = [_call("check_deprecation", endpoint="create_issue", api_version="2025-06-01")]
    assert classify_failure_mode(CASE, calls) is None


def test_argument_is_valid_rejects_a_made_up_endpoint():
    assert argument_is_valid(_call("get_openapi_spec", endpoint="delete_everything", api_version="2025-06-01")) is False
    assert argument_is_valid(_call("get_openapi_spec", endpoint="create_issue", api_version="2025-06-01")) is True


def test_tool_choice_accuracy_counts_legitimate_tools_for_the_case():
    calls = [
        _call("check_deprecation", endpoint="create_issue", api_version="2025-06-01"),
        _call("search_docs", query="x"),
    ]
    correct, total = tool_choice_accuracy(CASE, calls)
    assert (correct, total) == (1, 2)


def test_summarize_computes_gap_as_outcome_minus_trajectory():
    records = [
        {"outcome_passed": True, "trajectory_passed": True, "steps_taken": 1, "min_steps": 1,
         "tool_choice_correct": 1, "tool_choice_total": 1, "valid_arg_calls": 1, "total_arg_calls": 1,
         "total_cost_usd": 0.01},
        {"outcome_passed": True, "trajectory_passed": False, "steps_taken": 0, "min_steps": 1,
         "tool_choice_correct": 0, "tool_choice_total": 0, "valid_arg_calls": 0, "total_arg_calls": 0,
         "total_cost_usd": 0.02},
    ]
    summary = summarize(records)
    assert summary["outcome_pass_rate"] == 1.0
    assert summary["trajectory_pass_rate"] == 0.5
    assert round(summary["outcome_minus_trajectory_gap"], 4) == 0.5
    assert summary["cost_p50_usd"] == 0.015
    assert summary["cost_max_usd"] == 0.02


def test_find_gap_examples_returns_only_right_answer_wrong_path():
    records = [
        {"id": "a", "outcome_passed": True, "trajectory_passed": False},
        {"id": "b", "outcome_passed": True, "trajectory_passed": True},
        {"id": "c", "outcome_passed": False, "trajectory_passed": False},
    ]
    assert [r["id"] for r in find_gap_examples(records)] == ["a"]


def test_mode_counts_ignores_passing_records():
    records = [{"failure_mode": None}, {"failure_mode": "no_tool_call"}, {"failure_mode": "no_tool_call"}]
    assert mode_counts(records) == {"no_tool_call": 2}
