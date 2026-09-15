import json

from eval.week7.budget_demo import run_and_log
from tests.week7_fakes import FakeGroqClient, FakeToolCall, fake_response


def test_run_and_log_writes_a_clean_budget_termination(tmp_path):
    # check_deprecation, not search_docs: lap 1's tool call actually
    # executes before the budget trips on lap 2, and this one is a pure
    # JSON lookup with no real Chroma/embedding-model side effect.
    tool_call = FakeToolCall(
        "call_1", "check_deprecation", json.dumps({"endpoint": "create_issue", "api_version": "2025-06-01"})
    )
    client = FakeGroqClient([fake_response(tool_calls=[tool_call])])
    log_path = tmp_path / "budget_termination.log"

    result_path = run_and_log(
        "I'm creating an issue on 2025-06-01 with assignee -- what should I use instead?",
        client=client,
        log_path=log_path,
    )

    contents = result_path.read_text()
    assert "max_iterations" in contents
    assert "terminated" in contents.lower()
