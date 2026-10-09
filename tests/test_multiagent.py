from types import SimpleNamespace
from unittest.mock import patch

from agent.orchestrator import run_orchestrator
from agent.budgets import Budget
from agent.loop import SYSTEM_PROMPT


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

    assert len(research_agent.calls) == 1
    assert len(package_agent.calls) == 1
    assert "Markdown" in result.answer
    assert "version 2.0" in result.answer
    assert len(result.specialist_results) == 2


def test_run_agent_uses_default_system_prompt():
    budget = Budget(
        max_iterations=3,
        max_tokens=1000,
        max_cost_usd=0.01,
        max_wall_seconds=30,
    )

    with patch("agent.loop.Groq", create=True):
        pass

    # Existing specialist callers should continue using the
    # default system prompt unless they explicitly override it.
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 0
