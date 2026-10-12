"""End-to-end: real Specialist -> real MCP registry -> real stdio server,
with a scripted LLM standing in for Groq."""

import json
from types import SimpleNamespace as NS

import pytest

from agent.budgets import Budget
from agent.specialists import Specialist
from agent.squad import run_squad

PROBE = "tests/fixtures/mcp_probe_server.py"


def _tc(call_id, name, args):
    return NS(id=call_id, function=NS(name=name, arguments=args if isinstance(args, str) else json.dumps(args)))


class ScriptedClient:
    def __init__(self, route, steps, synth="FINAL"):
        self.route, self.steps, self.synth = route, list(steps), synth
        self.messages = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, model, messages, tools=None, tool_choice=None):
        self.messages.append(messages)
        usage = NS(prompt_tokens=1, completion_tokens=1)
        if tools is None:
            text = self.route if messages[0]["content"].startswith("You are the routing") else self.synth
            return NS(choices=[NS(message=NS(content=text, tool_calls=None))], usage=usage)
        step = self.steps.pop(0)
        msg = NS(content=step, tool_calls=None) if isinstance(step, str) else NS(content=None, tool_calls=step)
        return NS(choices=[NS(message=msg)], usage=usage)


@pytest.fixture
def squad(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")
    monkeypatch.setattr("agent.squad.time.sleep", lambda s: None)
    budget = Budget(max_iterations=4, max_tokens=10_000, max_cost_usd=1, max_wall_seconds=60)
    worker = Specialist("probe_worker", "Echo specialist.", [PROBE], budget)
    yield worker
    worker.close()


def test_routing_prompt_uses_discovered_tools(squad):
    from agent.squad import build_routing_prompt
    assert "echo" in build_routing_prompt([squad])


def test_tool_result_propagates_with_evidence(squad):
    client = ScriptedClient("probe_worker", [[_tc("1", "echo", {"text": "hi"})], "It echoed hi."])
    result = run_squad("say hi", [squad], client=client)
    assert result.status == "completed"
    call = result.evidence["probe_worker"][0]
    assert call["tool"] == "echo" and call["status"] == "ok" and "hi" in call["result_excerpt"]
    assert "hi" in client.messages[-1][1]["content"]  # evidence reached synthesis


def test_fabricated_answer_after_tool_error_is_rejected_not_synthesized(squad):
    client = ScriptedClient("probe_worker", [
        [_tc("1", "echo", {})], "All good, nothing to report.",       # attempt 1: invalid args, then claims success
        [_tc("2", "echo", {})], "All good, nothing to report.",       # attempt 2: same
    ])
    result = run_squad("q", [squad], client=client)
    assert result.status == "paused_input_required"
    assert "no successful tool evidence" in result.answer


def test_malformed_tool_json_is_recoverable_inside_one_attempt(squad):
    client = ScriptedClient("probe_worker", [
        [_tc("1", "echo", "{bad")], [_tc("2", "echo", {"text": "ok"})], "done",
    ])
    result = run_squad("q", [squad], client=client)
    assert result.status == "completed"
    assert [c["status"] for c in result.evidence["probe_worker"]] == ["error", "ok"]


def test_budget_exhaustion_is_reported_as_failure(squad):
    steps = [[_tc(str(i), "echo", {"text": str(i)})] for i in range(10)]
    client = ScriptedClient("probe_worker", steps)
    result = run_squad("q", [squad], client=client)
    assert result.status == "paused_input_required"
    assert "budget" in result.answer
