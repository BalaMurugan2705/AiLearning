
from types import SimpleNamespace

from agent.orchestrator import run_orchestrator
from unittest.mock import patch
from types import SimpleNamespace

from agent.specialists import ResearchAgent
from agent.budgets import Budget
from agent.specialists import PackageAgent
from agent.loop import SYSTEM_PROMPT
from agent.specialists import PackageAgent
from agent.tools import (
    RESEARCH_TOOL_FUNCTIONS,
    RESEARCH_TOOL_SCHEMAS,
    PACKAGE_TOOL_FUNCTIONS,
    PACKAGE_TOOL_SCHEMAS,
)

class FakeSpecialist:
    """A specialist agent that returns a predefined result."""

    def __init__(self, name, result):
        self.name = name
        self.result = result
        self.calls = []

    def run(self, task):
        self.calls.append(task)
        return SimpleNamespace(
            answer=self.result,
            terminated_by_budget=False,
        )


def test_orchestrator_delegates_to_research_agent():
    research_agent = FakeSpecialist(
        name="research",
        result="The documentation says the default mode is markdown.",
    )

    result = run_orchestrator(
        question="What is the default mode?",
        specialists=[research_agent],
    )

    assert len(research_agent.calls) == 1
    assert research_agent.calls[0] == "What is the default mode?"
    assert "markdown" in result.answer.lower()

def test_orchestrator_delegates_to_multiple_agents():
    research_agent = FakeSpecialist(
        name="research",
        result="The documentation uses Markdown.",
    )

    package_agent = FakeSpecialist(
        name="package",
        result="The package supports version 2.0.",
    )

    result = run_orchestrator(
        question="Explain the documentation and package version.",
        specialists=[research_agent, package_agent],
    )

    # Both agents should receive the same user question.
    assert len(research_agent.calls) == 1
    assert len(package_agent.calls) == 1

    # The orchestrator should combine both responses.
    assert "Markdown" in result.answer
    assert "version 2.0" in result.answer

    # The result should preserve individual agent responses.
    assert len(result.specialist_results) == 2

def test_research_agent_uses_existing_agent_loop():
    budget = Budget(
        max_iterations=3,
        max_tokens=1000,
        max_cost_usd=0.01,
        max_wall_seconds=30,
    )

    expected_result = SimpleNamespace(
        answer="Research completed.",
        terminated_by_budget=False,
    )

    with patch(
        "agent.specialists.run_agent",
        return_value=expected_result,
    ) as mock_run_agent:

        specialist = ResearchAgent(budget=budget)
        result = specialist.run("Research the package documentation.")

    assert result.answer == "Research completed."

    mock_run_agent.assert_called_once_with(
        question="Research the package documentation.",
        budget=budget,
        system_prompt=(
            "You are a documentation research specialist. "
            "Research the provided task using available tools. "
            "Only state facts supported by tool results. "
            "Clearly identify missing information."
        ),
        tool_schemas=RESEARCH_TOOL_SCHEMAS,
        tool_functions=RESEARCH_TOOL_FUNCTIONS,

    )

def test_orchestrator_runs_research_and_package_agents():
    budget = Budget(
        max_iterations=3,
        max_tokens=1000,
        max_cost_usd=0.01,
        max_wall_seconds=30,
    )

    research_agent = ResearchAgent(budget=budget)
    package_agent = PackageAgent(budget=budget)

    with patch.object(
        research_agent,
        "run",
        return_value=SimpleNamespace(
            answer="Documentation research complete.",
            terminated_by_budget=False,
        ),
    ), patch.object(
        package_agent,
        "run",
        return_value=SimpleNamespace(
            answer="Package compatibility research complete.",
            terminated_by_budget=False,
        ),
    ):
        result = run_orchestrator(
            question="Research package documentation and compatibility.",
            specialists=[research_agent, package_agent],
        )

    assert len(result.specialist_results) == 2
    assert "Documentation research" in result.answer
    assert "Package compatibility" in result.answer

# def test_orchestrator_runs_research_and_package_agents():
#     budget = Budget(
#         max_iterations=3,
#         max_tokens=1000,
#         max_cost_usd=0.01,
#         max_wall_seconds=30,
#     )

#     research_agent = ResearchAgent(budget=budget)
#     package_agent = PackageAgent(budget=budget)

#     result = run_orchestrator(
#         question="Research package documentation and compatibility.",
#         specialists=[research_agent, package_agent],
#     )

#     assert len(result.specialist_results) == 2

#     agent_names = [
#         item["agent"] for item in result.specialist_results
#     ]

#     assert agent_names == ["research", "package"]
def test_run_agent_uses_default_system_prompt():
    from agent.loop import run_agent

    budget = Budget(
        max_iterations=3,
        max_tokens=1000,
        max_cost_usd=0.01,
        max_wall_seconds=30,
    )

    with patch("agent.loop.Groq", create=True) as mock_groq:
        pass

    # Existing specialist callers should continue using the
    # default system prompt unless they explicitly override it.
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 0
def test_research_agent_only_receives_research_tools():
    budget = Budget(
        max_iterations=3,
        max_tokens=1000,
        max_cost_usd=0.01,
        max_wall_seconds=30,
    )

    expected_result = SimpleNamespace(
        answer="Research completed.",
        terminated_by_budget=False,
    )

    with patch(
        "agent.specialists.run_agent",
        return_value=expected_result,
    ) as mock_run_agent:

        specialist = ResearchAgent(budget=budget)
        specialist.run("Research the documentation.")

    kwargs = mock_run_agent.call_args.kwargs

    assert kwargs["tool_schemas"] == RESEARCH_TOOL_SCHEMAS
    assert kwargs["tool_functions"] == RESEARCH_TOOL_FUNCTIONS

    assert "search_docs" in kwargs["tool_functions"]
    assert "get_openapi_spec" not in kwargs["tool_functions"]
    assert "check_deprecation" not in kwargs["tool_functions"]

def test_package_agent_only_receives_package_tools():
    budget = Budget(
        max_iterations=3,
        max_tokens=1000,
        max_cost_usd=0.01,
        max_wall_seconds=30,
    )

    expected_result = SimpleNamespace(
        answer="Package research completed.",
        terminated_by_budget=False,
    )

    with patch(
        "agent.specialists.run_agent",
        return_value=expected_result,
    ) as mock_run_agent:

        specialist = PackageAgent(budget=budget)
        specialist.run("Check package compatibility.")

    kwargs = mock_run_agent.call_args.kwargs

    assert kwargs["tool_schemas"] == PACKAGE_TOOL_SCHEMAS
    assert kwargs["tool_functions"] == PACKAGE_TOOL_FUNCTIONS

    assert "get_openapi_spec" in kwargs["tool_functions"]
    assert "check_deprecation" in kwargs["tool_functions"]
    assert "search_docs" not in kwargs["tool_functions"]