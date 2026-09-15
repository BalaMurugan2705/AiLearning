from agent.workflow import extract_api_version, extract_endpoint, run_workflow
from tests.week7_fakes import FakeGroqClient, fake_response


def test_extract_endpoint_matches_known_keywords():
    assert extract_endpoint("Is the assignee field deprecated for creating an issue?") == "create_issue"
    assert extract_endpoint("What changed for creating a pull request?") == "create_pull_request"


def test_extract_endpoint_returns_none_when_no_keyword_matches():
    assert extract_endpoint("What's the weather today?") is None


def test_extract_api_version_finds_explicit_version_in_question():
    assert extract_api_version("On 2022-11-28, what does assignee look like?") == "2022-11-28"


def test_extract_api_version_defaults_to_newest_when_unstated():
    assert extract_api_version("What does assignee look like?") == "2025-06-01"


def test_run_workflow_calls_all_three_tools_then_generates_once():
    # Only the generation call is faked -- search_docs really runs against
    # agent.tools's module-level pipeline, so this test's first run builds
    # (and persists into the project's real chroma_db/) the "week7_docs"
    # collection, same as tests/test_week7_corpus.py -- the point here is
    # verifying the workflow's real tool sequence, not mocking it away.
    client = FakeGroqClient([fake_response(content="Use assignees instead of assignee.")])
    result = run_workflow(
        "Is assignee deprecated for creating an issue in 2025-06-01?", client=client
    )
    tool_names = [m["name"] for m in result.transcript if m.get("role") == "tool"]
    assert tool_names == ["search_docs", "get_openapi_spec", "check_deprecation"]
    assert len(client.calls) == 1  # exactly one generation call -- no loop
    assert "assignees" in result.answer
    assert result.terminated_by_budget is False
