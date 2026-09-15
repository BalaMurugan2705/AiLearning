import json

from agent.budgets import Budget
from agent.loop import run_agent
from tests.week7_fakes import FakeGroqClient, FakeToolCall, fake_response


def _generous_budget():
    return Budget(max_iterations=5, max_tokens=100_000, max_cost_usd=10.0, max_wall_seconds=60.0)


def test_agent_answers_directly_when_no_tool_call_needed():
    client = FakeGroqClient([fake_response(content="The default mode is markdown.")])
    result = run_agent("What is the default mode?", budget=_generous_budget(), client=client)
    assert result.terminated_by_budget is False
    assert "markdown" in result.answer
    assert result.iterations == 1


def test_agent_calls_a_tool_then_answers():
    tool_call = FakeToolCall("call_1", "check_deprecation", json.dumps({"endpoint": "create_issue", "api_version": "2025-06-01"}))
    client = FakeGroqClient([
        fake_response(tool_calls=[tool_call]),
        fake_response(content="Use assignees instead of assignee."),
    ])
    result = run_agent("Is assignee deprecated for creating issues in 2025-06-01?", budget=_generous_budget(), client=client)
    assert result.iterations == 2
    assert "assignees" in result.answer
    assert result.transcript[-1]["role"] == "assistant"


def test_agent_sums_tokens_across_every_lap_not_just_the_last_call():
    # check_deprecation, not search_docs: a pure JSON lookup, so this test
    # stays fast and has no side effect on the real Chroma index.
    tool_call = FakeToolCall(
        "call_1", "check_deprecation", json.dumps({"endpoint": "create_issue", "api_version": "2025-06-01"})
    )
    client = FakeGroqClient([
        fake_response(tool_calls=[tool_call], prompt_tokens=100, completion_tokens=20),
        fake_response(content="done", prompt_tokens=150, completion_tokens=10),
    ])
    result = run_agent("q", budget=_generous_budget(), client=client)
    assert result.total_tokens == (100 + 20) + (150 + 10)


def test_agent_stops_cleanly_when_max_iterations_exceeded():
    # check_deprecation again, so lap 1's tool execution stays a fast, pure
    # JSON lookup instead of touching the real Chroma index.
    tool_call = FakeToolCall(
        "call_1", "check_deprecation", json.dumps({"endpoint": "create_issue", "api_version": "2025-06-01"})
    )
    # Only one fake response queued: the tracker must trip on iteration 2's
    # start_iteration(), *before* a second .create() call is attempted.
    client = FakeGroqClient([fake_response(tool_calls=[tool_call])])
    tight_budget = Budget(max_iterations=1, max_tokens=100_000, max_cost_usd=10.0, max_wall_seconds=60.0)
    result = run_agent("q", budget=tight_budget, client=client)
    assert result.terminated_by_budget is True
    assert "max_iterations" in result.budget_reason
    assert result.answer is None


def test_agent_stops_cleanly_when_max_tokens_exceeded():
    client = FakeGroqClient([fake_response(content="ignored", prompt_tokens=500, completion_tokens=600)])
    tight_budget = Budget(max_iterations=5, max_tokens=100, max_cost_usd=10.0, max_wall_seconds=60.0)
    result = run_agent("q", budget=tight_budget, client=client)
    assert result.terminated_by_budget is True
    assert "max_tokens" in result.budget_reason
