# Generic MCP-Backed Specialist Squad Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four bespoke, inconsistently-wired specialist classes (`ResearchAgent`, `PackageAgent`, `DeprecationWorker`, `CodeSampleWorker`) and two orchestration entry points (`run_squad`, `run_orchestrator`) with one config-driven `Specialist` class that sources its tools dynamically from MCP, and one generalized `run_squad` that routes, retries, and gracefully degrades uniformly across however many specialists are configured.

**Architecture:** A new `specialists.json` declares `{name, description, mcp_servers}` per specialist. `agent/specialists.py`'s `Specialist` class discovers its tools from those MCP servers at construction time (via the existing `build_multi_mcp_tool_registry`) and auto-appends a grounding line naming exactly those discovered tools to its system prompt. `agent/squad.py`'s `run_squad` loads a list of `Specialist` instances, routes a question to zero-or-more of them with one LLM call, runs routed specialists sequentially through one shared retry wrapper, and synthesizes an answer from whatever succeeded — pausing for user input only if every routed specialist failed. `agent/orchestrator.py` is deleted outright.

**Tech Stack:** Python, pytest, `unittest.mock.patch`, the existing MCP Python SDK plumbing in `agent/mcp_adapter.py` (unchanged), Groq's OpenAI-SDK-compatible client (mocked in all new tests via a fake client object).

**Spec:** `docs/superpowers/specs/2026-10-08-generic-mcp-squad-design.md` — this plan implements that spec section-by-section; read it alongside this plan for the "why" behind each decision.

## Global Constraints

- Retry attempts stay fixed at 2 (1 retry) per specialist — not configurable, matches the spec's explicit "out of scope: changing the retry attempt count."
- Routed specialists execute sequentially, never in parallel (spec section 5 / "out of scope" section 9).
- Pause (`status="paused_input_required"`) fires only when **every routed** specialist failed; any single success still produces `status="completed"` with synthesis noting the gap (spec section 6).
- `force_failure` matches by specialist `name` generically — never hardcode a specific worker name in `agent/squad.py` again.
- Do not modify `agent/mcp_adapter.py`, `agent/loop.py`, `agent/mcp_servers/*.py`, `mcp_config.json`, or `capture_error_transcript.py` — confirmed unaffected/out of scope by the spec.
- Keep `agent/tools.py`'s `TOOL_SCHEMAS`, `TOOL_FUNCTIONS`, `call_tool`, `search_docs`, `get_openapi_spec`, `check_deprecation` untouched — they back the single-agent baseline and the MCP servers respectively, neither of which this change touches.
- `handoffs.log` entries keep the existing shape (`case_id`, `hop`, `status`, `tokens`, plus `attempts`/`error`/`decision` where applicable) — `eval/week10/race.py`'s `attribute_bottleneck` parses this file and must keep working unmodified.

## Review Focus

- A `specialists.json` with only one entry — routing, execution, and synthesis must still work when there's nothing to split a decision between. → tested in Task 3 (`test_run_squad_works_with_a_single_configured_specialist`).
- `force_failure` set to a name that matches no configured specialist — must silently have no effect (specialist succeeds normally) rather than raising or injecting failure into the wrong specialist. → tested in Task 3 (`test_run_specialist_with_retry_force_failure_name_mismatch_does_not_trigger`).
- An empty or whitespace-only routing response from the model (not just an unparseable one) — must still fail open to "route to all," not crash on `.lower()`/`.strip()` of an unexpected value. → tested in Task 3 (`test_decide_route_falls_back_to_all_on_empty_response`).
- A specialist whose MCP server fails to start during discovery (not during a run) — this happens at `Specialist.__init__`/`load_specialists` time, outside the retry wrapper entirely, so it must propagate loudly instead of being silently swallowed or mistaken for a retryable run-time failure. → tested in Task 2 (`test_load_specialists_propagates_mcp_discovery_errors`).
- The specific bug this whole redesign fixes: whichever specialist fails (not just the first/"primary" one) gets identical retry and partial-failure-synthesis treatment — no positional asymmetry. → tested in Task 3 (`test_run_squad_synthesizes_from_partial_failure_when_second_specialist_fails`, mirroring the existing first-specialist-fails case).

---

### Task 1: Add the `specialists.json` config

**Files:**
- Create: `specialists.json`

**Interfaces:**
- Produces: a JSON file read by `load_specialists` (Task 2) — shape `{"specialists": [{"name": str, "description": str, "mcp_servers": [str, ...]}, ...]}`.

- [ ] **Step 1: Create the config file**

```json
{
  "specialists": [
    {
      "name": "deprecation_worker",
      "description": "You are the version/deprecation specialist on a GitHub API migration team. Exact parameter shapes, deprecation status, and version diffs for one named GitHub endpoint and API version. Answer only using tool results. State exact parameter names and whether something is deprecated. Never guess a version fact you did not get from a tool.",
      "mcp_servers": ["agent/mcp_servers/package_server.py"]
    },
    {
      "name": "code_sample_worker",
      "description": "You are the code-sample specialist on a GitHub API migration team. Prose documentation search for any other kind of fact (limits, scopes, IDs, general behavior, how something works). Use the documentation search tool to find the relevant fact, then answer with a one- or two-line explanation plus a short code snippet illustrating it. Only use facts the tool actually returned.",
      "mcp_servers": ["agent/mcp_servers/docs_server.py"]
    }
  ]
}
```

- [ ] **Step 2: Verify it's valid JSON and has the expected shape**

Run: `python3 -c "import json; d = json.load(open('specialists.json')); assert len(d['specialists']) == 2; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add specialists.json
git commit -m "Add specialists.json config for MCP-backed squad specialists"
```

---

### Task 2: Replace `ResearchAgent`/`PackageAgent` with a generic `Specialist` (agent/specialists.py)

**Files:**
- Modify: `agent/specialists.py` (full rewrite)
- Modify: `tests/test_multiagent.py` (remove tests that depend on the retired `ResearchAgent`/`PackageAgent` classes)
- Create: `tests/test_specialists.py`

**Interfaces:**
- Consumes: `build_multi_mcp_tool_registry(server_scripts: list[str]) -> (tool_schemas: list[dict], tool_functions: dict[str, callable])` from `agent.mcp_adapter` (unchanged); `run_agent(question, budget, client=None, system_prompt=None, tool_schemas=None, tool_functions=None)` from `agent.loop` (unchanged); `Budget` dataclass from `agent.budgets` (unchanged).
- Produces: `Specialist(name: str, description: str, mcp_servers: list[str], budget: Budget)` with `.name`, `.description`, `.tool_schemas`, `.tool_functions`, `.system_prompt`, and `.run(task: str, client=None)`. `load_specialists(config_path: Path, budget: Budget) -> list[Specialist]`, used by Task 3 (`run_squad`'s caller), Task 5, 6, 7.

- [ ] **Step 1: Write the failing tests for `Specialist` and `load_specialists`**

Create `tests/test_specialists.py`:

```python
import json

import pytest
from unittest.mock import patch

from agent.budgets import Budget
from agent.specialists import Specialist, load_specialists


def _budget():
    return Budget(max_iterations=3, max_tokens=1000, max_cost_usd=0.01, max_wall_seconds=30)


def test_specialist_builds_tools_and_grounded_system_prompt():
    fake_schemas = [{"type": "function", "function": {"name": "search_documentation", "parameters": {}}}]
    fake_functions = {"search_documentation": lambda **kwargs: "ok"}

    with patch(
        "agent.specialists.build_multi_mcp_tool_registry",
        return_value=(fake_schemas, fake_functions),
    ) as mock_build:
        specialist = Specialist(
            name="code_sample_worker",
            description="Prose documentation search specialist.",
            mcp_servers=["agent/mcp_servers/docs_server.py"],
            budget=_budget(),
        )

    mock_build.assert_called_once_with(["agent/mcp_servers/docs_server.py"])
    assert specialist.name == "code_sample_worker"
    assert specialist.tool_schemas == fake_schemas
    assert specialist.tool_functions == fake_functions
    assert "Prose documentation search specialist." in specialist.system_prompt
    assert "search_documentation" in specialist.system_prompt


def test_specialist_run_delegates_to_run_agent_with_its_own_tools():
    fake_schemas = [{"type": "function", "function": {"name": "search_documentation", "parameters": {}}}]
    fake_functions = {"search_documentation": lambda **kwargs: "ok"}

    with patch(
        "agent.specialists.build_multi_mcp_tool_registry",
        return_value=(fake_schemas, fake_functions),
    ):
        specialist = Specialist(
            name="code_sample_worker",
            description="Prose documentation search specialist.",
            mcp_servers=["agent/mcp_servers/docs_server.py"],
            budget=_budget(),
        )

    with patch("agent.specialists.run_agent") as mock_run_agent:
        mock_run_agent.return_value = "sentinel-result"
        result = specialist.run("What are the body params for create_issue?", client="fake-client")

    assert result == "sentinel-result"
    mock_run_agent.assert_called_once_with(
        question="What are the body params for create_issue?",
        budget=specialist.budget,
        client="fake-client",
        system_prompt=specialist.system_prompt,
        tool_schemas=fake_schemas,
        tool_functions=fake_functions,
    )


def test_load_specialists_builds_one_specialist_per_config_entry(tmp_path):
    config_path = tmp_path / "specialists.json"
    config_path.write_text(json.dumps({
        "specialists": [
            {
                "name": "deprecation_worker",
                "description": "Deprecation specialist.",
                "mcp_servers": ["agent/mcp_servers/package_server.py"],
            },
            {
                "name": "code_sample_worker",
                "description": "Code sample specialist.",
                "mcp_servers": ["agent/mcp_servers/docs_server.py"],
            },
        ]
    }))

    with patch(
        "agent.specialists.build_multi_mcp_tool_registry",
        return_value=([], {}),
    ) as mock_build:
        specialists = load_specialists(config_path, budget=_budget())

    assert [s.name for s in specialists] == ["deprecation_worker", "code_sample_worker"]
    assert mock_build.call_count == 2


def test_load_specialists_propagates_mcp_discovery_errors(tmp_path):
    config_path = tmp_path / "specialists.json"
    config_path.write_text(json.dumps({
        "specialists": [
            {
                "name": "broken_worker",
                "description": "A specialist whose server fails to start.",
                "mcp_servers": ["agent/mcp_servers/does_not_exist.py"],
            },
        ]
    }))

    with patch(
        "agent.specialists.build_multi_mcp_tool_registry",
        side_effect=RuntimeError("server process exited"),
    ):
        with pytest.raises(RuntimeError, match="server process exited"):
            load_specialists(config_path, budget=_budget())
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_specialists.py -v`
Expected: FAIL (collection error) — `agent.specialists` has no attribute `Specialist`/`load_specialists` yet.

- [ ] **Step 3: Rewrite `agent/specialists.py`**

Replace the entire file:

```python
import json
from pathlib import Path

from agent.budgets import Budget
from agent.loop import run_agent
from agent.mcp_adapter import build_multi_mcp_tool_registry

REPO_ROOT = Path(__file__).resolve().parent.parent


class Specialist:
    """A specialist agent whose tools are discovered dynamically from one
    or more MCP servers, instead of calling local Python functions
    directly. Construction (and MCP discovery) happens once; .run() can
    be called for any number of questions afterward.
    """

    def __init__(self, name: str, description: str, mcp_servers: list[str], budget: Budget):
        self.name = name
        self.description = description
        self.budget = budget

        self.tool_schemas, self.tool_functions = build_multi_mcp_tool_registry(mcp_servers)

        self.system_prompt = (
            f"{description}\n\n"
            f"The only tools available to you are: {', '.join(sorted(self.tool_functions))}. "
            "Use only these -- never invent a tool name."
        )

    def run(self, task: str, client=None):
        return run_agent(
            question=task,
            budget=self.budget,
            client=client,
            system_prompt=self.system_prompt,
            tool_schemas=self.tool_schemas,
            tool_functions=self.tool_functions,
        )


def load_specialists(config_path: Path, budget: Budget) -> list[Specialist]:
    """Build one Specialist per entry in a specialists.json-shaped config
    file. MCP server paths in the config are resolved relative to the
    repo root, same convention test_mcp_research.py already used for
    mcp_config.json.
    """

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))

    specialists = []
    for entry in config["specialists"]:
        mcp_servers = [
            str(REPO_ROOT / server_path) for server_path in entry["mcp_servers"]
        ]
        specialists.append(
            Specialist(
                name=entry["name"],
                description=entry["description"],
                mcp_servers=mcp_servers,
                budget=budget,
            )
        )
    return specialists
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest tests/test_specialists.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Remove tests in `tests/test_multiagent.py` that depend on the retired `ResearchAgent`/`PackageAgent` classes**

Replace the entire file `tests/test_multiagent.py` with:

```python
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
```

(The `run_orchestrator`-dependent tests above are removed in Task 4, once `agent/orchestrator.py` itself is deleted — they still pass today, so they stay for now.)

- [ ] **Step 6: Run the full test file to confirm nothing is broken**

Run: `pytest tests/test_multiagent.py tests/test_specialists.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add agent/specialists.py tests/test_specialists.py tests/test_multiagent.py
git commit -m "Replace ResearchAgent/PackageAgent with generic MCP-backed Specialist"
```

---

### Task 3: Generalize `run_squad` routing, retry, and partial-failure synthesis (agent/squad.py)

**Files:**
- Modify: `agent/squad.py` (full rewrite)
- Create: `tests/test_squad.py`

**Interfaces:**
- Consumes: `Specialist` from `agent.specialists` (Task 2) — duck-typed as anything with `.name: str` and `.run(question: str, client=None) -> object with .answer, .total_tokens, .total_cost_usd`. `AGENT_MODEL`, `price_for` from `agent.config` (unchanged).
- Produces: `run_squad(question: str, specialists: list[Specialist], client=None, case_id: str | None = None, force_failure: str | None = None) -> SquadResult`. `SquadResult(answer, status, total_tokens, total_cost_usd, wall_seconds, handoffs)` (unchanged shape). Internal (used directly by this task's own tests): `build_routing_prompt(specialists) -> str`, `_decide_route(question, specialists, client) -> (set[str], str, int, float)`, `_run_specialist_with_retry(specialist, question, client, force_failure=None, max_attempts=2) -> (result_or_None, error_or_None, attempts)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_squad.py`:

```python
from dataclasses import dataclass
from types import SimpleNamespace

from agent.squad import (
    build_routing_prompt,
    _decide_route,
    _run_specialist_with_retry,
    run_squad,
)


@dataclass
class FakeNamed:
    name: str
    description: str


class FakeSpecialist:
    def __init__(self, name, result=None, fail_times=0):
        self.name = name
        self.description = f"{name} description"
        self._result = result
        self._fail_times = fail_times
        self.call_count = 0

    def run(self, task, client=None):
        self.call_count += 1
        if self.call_count <= self._fail_times:
            raise RuntimeError(f"{self.name} unavailable")
        return self._result


class FakeClient:
    """Stands in for the Groq client. Each call to chat.completions.create
    pops the next canned response, in call order (routing first, then
    synthesis if it happens)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.sent_messages = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages):
        self.sent_messages.append(messages)
        content = self._responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


def _specialist_result(answer):
    return SimpleNamespace(answer=answer, total_tokens=20, total_cost_usd=0.002)


def test_build_routing_prompt_lists_every_specialist():
    specialists = [FakeNamed("a", "desc A"), FakeNamed("b", "desc B")]
    prompt = build_routing_prompt(specialists)
    assert "a" in prompt and "desc A" in prompt
    assert "b" in prompt and "desc B" in prompt


def test_decide_route_matches_named_specialist():
    specialists = [FakeNamed("deprecation_worker", "d"), FakeNamed("code_sample_worker", "c")]
    client = FakeClient(["deprecation_worker"])
    matched, normalized, tokens, cost = _decide_route("q", specialists, client)
    assert matched == {"deprecation_worker"}


def test_decide_route_falls_back_to_all_when_unparseable():
    specialists = [FakeNamed("deprecation_worker", "d"), FakeNamed("code_sample_worker", "c")]
    client = FakeClient(["I'm not sure"])
    matched, normalized, tokens, cost = _decide_route("q", specialists, client)
    assert matched == {"deprecation_worker", "code_sample_worker"}


def test_decide_route_falls_back_to_all_on_empty_response():
    specialists = [FakeNamed("deprecation_worker", "d"), FakeNamed("code_sample_worker", "c")]
    client = FakeClient([""])
    matched, normalized, tokens, cost = _decide_route("q", specialists, client)
    assert matched == {"deprecation_worker", "code_sample_worker"}


def test_run_specialist_with_retry_succeeds_first_try():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"))
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure=None,
    )
    assert result.answer == "ok"
    assert error is None
    assert attempts == 1


def test_run_specialist_with_retry_succeeds_on_retry():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"), fail_times=1)
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure=None,
    )
    assert result.answer == "ok"
    assert attempts == 2


def test_run_specialist_with_retry_gives_up_after_max_attempts():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"), fail_times=5)
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure=None,
    )
    assert result is None
    assert attempts == 2
    assert "worker unavailable" in error


def test_run_specialist_with_retry_force_failure_matches_by_name():
    specialist = FakeSpecialist("custom_worker", result=_specialist_result("ok"))
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure="custom_worker",
    )
    assert result is None
    assert "custom_worker service unavailable" in error


def test_run_specialist_with_retry_force_failure_name_mismatch_does_not_trigger():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"))
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure="some_other_worker",
    )
    assert result.answer == "ok"
    assert error is None
    assert attempts == 1


def test_run_squad_routes_to_one_specialist_and_skips_the_other(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    dep = FakeSpecialist("deprecation_worker", result=_specialist_result("dep answer"))
    code = FakeSpecialist("code_sample_worker", result=_specialist_result("code answer"))
    client = FakeClient(["deprecation_worker", "final synthesized answer"])

    result = run_squad("q", [dep, code], client=client)

    assert result.status == "completed"
    assert code.call_count == 0
    assert dep.call_count == 1
    assert result.answer == "final synthesized answer"


def test_run_squad_synthesizes_from_partial_failure(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    dep = FakeSpecialist("deprecation_worker", result=None, fail_times=99)
    code = FakeSpecialist("code_sample_worker", result=_specialist_result("code answer"))
    client = FakeClient(["deprecation_worker, code_sample_worker", "final synthesized answer"])

    result = run_squad("q", [dep, code], client=client)

    assert result.status == "completed"
    synthesis_user_content = client.sent_messages[-1][1]["content"]
    assert "deprecation_worker" in synthesis_user_content
    assert "error" in synthesis_user_content.lower()


def test_run_squad_synthesizes_from_partial_failure_when_second_specialist_fails(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    dep = FakeSpecialist("deprecation_worker", result=_specialist_result("dep answer"))
    code = FakeSpecialist("code_sample_worker", result=None, fail_times=99)
    client = FakeClient(["deprecation_worker, code_sample_worker", "final synthesized answer"])

    result = run_squad("q", [dep, code], client=client)

    assert result.status == "completed"
    synthesis_user_content = client.sent_messages[-1][1]["content"]
    assert "code_sample_worker" in synthesis_user_content
    assert "error" in synthesis_user_content.lower()


def test_run_squad_pauses_when_all_routed_specialists_fail(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    dep = FakeSpecialist("deprecation_worker", result=None, fail_times=99)
    code = FakeSpecialist("code_sample_worker", result=None, fail_times=99)
    client = FakeClient(["deprecation_worker, code_sample_worker"])

    result = run_squad("q", [dep, code], client=client)

    assert result.status == "paused_input_required"
    assert len(client.sent_messages) == 1  # only the routing call -- synthesis never invoked


def test_run_squad_works_with_a_single_configured_specialist(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    only = FakeSpecialist("solo_worker", result=_specialist_result("solo answer"))
    client = FakeClient(["solo_worker", "final synthesized answer"])

    result = run_squad("q", [only], client=client)

    assert result.status == "completed"
    assert only.call_count == 1
    assert result.answer == "final synthesized answer"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_squad.py -v`
Expected: FAIL (collection error) — `build_routing_prompt`/`_decide_route`/`_run_specialist_with_retry` don't exist yet, and `DeprecationWorker`/`CodeSampleWorker` are still in `agent/squad.py`'s current form.

- [ ] **Step 3: Rewrite `agent/squad.py`**

Replace the entire file:

```python
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent.config import AGENT_MODEL, price_for
from agent.specialists import Specialist

REPO_ROOT = Path(__file__).resolve().parent.parent
HANDOFFS_LOG_PATH = REPO_ROOT / "handoffs.log"

SYNTHESIS_SYSTEM_PROMPT = (
    "You are the orchestrator for a GitHub API migration assistant team. "
    "You receive a user question plus answers from however many "
    "specialists were routed to it. Combine them into one clear answer. "
    "If a specialist's answer is marked as skipped or failed, say plainly "
    "that part of the information is unavailable -- never guess or invent "
    "the missing fact to fill the gap."
)


def build_routing_prompt(specialists: list[Specialist]) -> str:
    """Build the routing prompt from whatever specialists are configured,
    instead of a static prompt hardcoded to two named workers."""

    roster = "\n".join(f"- {s.name}: {s.description}" for s in specialists)
    names = ", ".join(repr(s.name) for s in specialists)
    return (
        "You are the routing step of a multi-specialist assistant team. "
        "The available specialists are:\n"
        f"{roster}\n\n"
        "Decide which specialist(s) are needed to answer the user's "
        "question. Reply with a comma-separated list of the exact "
        f"specialist name(s) that apply, chosen only from: {names}. "
        "If more than one applies, name all of them. If you are unsure, "
        "name every specialist that could plausibly help rather than "
        "guessing none."
    )


@dataclass
class SquadResult:
    answer: str
    status: str  # "completed" or "paused_input_required"
    total_tokens: int
    total_cost_usd: float
    wall_seconds: float
    handoffs: list[dict] = field(default_factory=list)


def _append_handoff(entry: dict) -> None:
    with open(HANDOFFS_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _call_llm(client, system_prompt: str, user_prompt: str):
    """One plain (no-tools) LLM call. Returns (text, tokens, cost_usd)."""
    response = client.chat.completions.create(
        model=AGENT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    usage = response.usage
    price_in, price_out = price_for(AGENT_MODEL)
    tokens = usage.prompt_tokens + usage.completion_tokens
    cost = (usage.prompt_tokens * price_in + usage.completion_tokens * price_out) / 1_000_000
    return response.choices[0].message.content, tokens, cost


def _decide_route(question: str, specialists: list[Specialist], client):
    """Ask the model which specialist(s) this question needs.

    Falls back to calling every specialist if the reply doesn't clearly
    name any of them -- silently answering with zero specialists would be
    a worse failure than occasionally calling one too many.
    """
    routing_prompt = build_routing_prompt(specialists)
    choice, tokens, cost = _call_llm(client, routing_prompt, question)
    normalized = (choice or "").strip().lower()

    valid_names = {s.name for s in specialists}
    matched = {name for name in valid_names if name.lower() in normalized}

    if not matched:
        matched = set(valid_names)

    return matched, normalized, tokens, cost


def _run_specialist_with_retry(
    specialist: Specialist,
    question: str,
    client,
    force_failure: str | None = None,
    max_attempts: int = 2,
):
    """Run one specialist with up to max_attempts tries.

    Returns (result_or_None, error_or_None, attempts_made). Applied
    identically to every specialist -- no specialist gets special-cased
    resilience that another lacks.
    """
    result = None
    error = None
    attempts = 0
    while attempts < max_attempts and result is None:
        attempts += 1
        try:
            if force_failure == specialist.name:
                raise RuntimeError(f"HTTP 500: {specialist.name} service unavailable")
            result = specialist.run(question, client=client)
        except Exception as exc:
            error = str(exc)
    return result, error, attempts


def run_squad(
    question: str,
    specialists: list[Specialist],
    client=None,
    case_id: str | None = None,
    force_failure: str | None = None,
) -> SquadResult:
    if client is None:
        from groq import Groq
        client = Groq()

    start = time.monotonic()
    total_tokens = 0
    total_cost = 0.0
    handoffs = []

    # --- Hop 0: routing decision ---
    routed_names, route_choice, route_tokens, route_cost = _decide_route(
        question, specialists, client
    )
    handoffs.append({
        "case_id": case_id,
        "hop": "orchestrator->routing_decision",
        "status": "ok",
        "decision": route_choice,
        "tokens": route_tokens,
    })
    total_tokens += route_tokens
    total_cost += route_cost

    # --- Run every specialist: routed ones with retry, others skipped ---
    outcomes = []
    for specialist in specialists:
        if specialist.name not in routed_names:
            handoffs.append({
                "case_id": case_id,
                "hop": f"orchestrator->{specialist.name}",
                "status": "skipped",
                "tokens": 0,
            })
            outcomes.append({"name": specialist.name, "status": "skipped", "answer": None, "error": None})
            continue

        result, error, attempts = _run_specialist_with_retry(
            specialist, question, client, force_failure=force_failure,
        )
        handoffs.append({
            "case_id": case_id,
            "hop": f"orchestrator->{specialist.name}",
            "status": "ok" if result else "error",
            "error": error if not result else None,
            "attempts": attempts,
            "tokens": result.total_tokens if result else 0,
        })

        if result:
            total_tokens += result.total_tokens
            total_cost += result.total_cost_usd
            outcomes.append({"name": specialist.name, "status": "ok", "answer": result.answer, "error": None})
        else:
            outcomes.append({"name": specialist.name, "status": "error", "answer": None, "error": error})

    # --- Pause only if every routed specialist failed ---
    routed_outcomes = [o for o in outcomes if o["status"] != "skipped"]
    if routed_outcomes and all(o["status"] == "error" for o in routed_outcomes):
        for entry in handoffs:
            _append_handoff(entry)
        failed_names = ", ".join(o["name"] for o in routed_outcomes)
        pause_message = (
            "I can't confirm this from any of the routed specialists right "
            f"now ({failed_names}). Do you want me to wait and try again "
            "later, or proceed with whatever other information is "
            "available?"
        )
        return SquadResult(
            answer=pause_message,
            status="paused_input_required",
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
            wall_seconds=time.monotonic() - start,
            handoffs=handoffs,
        )

    # --- Synthesis: combine whatever specialists actually produced ---
    answer_sections = []
    for outcome in outcomes:
        if outcome["status"] == "ok":
            answer_sections.append(f"{outcome['name']} answer:\n{outcome['answer']}")
        elif outcome["status"] == "error":
            answer_sections.append(
                f"{outcome['name']} answer:\n[error -- this specialist was "
                f"routed but failed after retrying: {outcome['error']}]"
            )
        else:
            answer_sections.append(
                f"{outcome['name']} answer:\n[skipped by router: question "
                "judged not to need this specialist]"
            )

    synthesis_prompt = (
        f"User question: {question}\n\n"
        + "\n\n".join(answer_sections)
        + "\n\nCombine these into one answer for the user."
    )
    final_answer, synth_tokens, synth_cost = _call_llm(
        client, SYNTHESIS_SYSTEM_PROMPT, synthesis_prompt
    )

    handoffs.append({
        "case_id": case_id,
        "hop": "orchestrator->synthesis_resend",
        "status": "ok",
        "tokens": synth_tokens,
    })
    total_tokens += synth_tokens
    total_cost += synth_cost

    for entry in handoffs:
        _append_handoff(entry)

    return SquadResult(
        answer=final_answer,
        status="completed",
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        wall_seconds=time.monotonic() - start,
        handoffs=handoffs,
    )
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest tests/test_squad.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Run the full test suite so far**

Run: `pytest tests/test_squad.py tests/test_specialists.py tests/test_multiagent.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add agent/squad.py tests/test_squad.py
git commit -m "Generalize run_squad routing, retry, and partial-failure synthesis"
```

---

### Task 4: Retire `run_orchestrator` (delete agent/orchestrator.py)

**Files:**
- Delete: `agent/orchestrator.py`
- Modify: `tests/test_multiagent.py` (remove the now-dead `run_orchestrator` tests)

**Interfaces:**
- Consumes: nothing (this task only removes code).
- Produces: nothing new — `run_squad` (Task 3) is the only orchestration entry point left in the codebase.

- [ ] **Step 1: Delete the file**

```bash
rm agent/orchestrator.py
```

- [ ] **Step 2: Remove the tests that depended on it**

Replace the entire file `tests/test_multiagent.py` with:

```python
from unittest.mock import patch

from agent.budgets import Budget
from agent.loop import SYSTEM_PROMPT


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
```

- [ ] **Step 3: Confirm nothing else references the deleted module**

Run: `grep -rln "agent.orchestrator\|run_orchestrator" --include="*.py" .`
Expected: no output (no matches)

- [ ] **Step 4: Run the test suite to confirm nothing broke**

Run: `pytest tests/test_multiagent.py tests/test_squad.py tests/test_specialists.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add -A agent/orchestrator.py tests/test_multiagent.py
git commit -m "Retire run_orchestrator -- run_squad is now the only orchestration entry point"
```

---

### Task 5: Point `test_mcp_research.py` at the new `Specialist`

**Files:**
- Modify: `test_mcp_research.py`

**Interfaces:**
- Consumes: `Specialist` from `agent.specialists` (Task 2).

- [ ] **Step 1: Replace the file's contents**

Replace the entire file `test_mcp_research.py`:

```python
"""One-off script: build a single Specialist that aggregates tools from
every MCP server listed in mcp_config.json, and run one research question
through it end-to-end over the real MCP servers. Adding/removing a server
is a config edit in mcp_config.json -- it never requires touching
agent/specialists.py or agent/mcp_adapter.py, which discover tools
dynamically from whatever servers are listed."""

import json
import os
from pathlib import Path

from agent.budgets import Budget
from agent.specialists import Specialist

PROJECT_ROOT = Path(__file__).resolve().parent

with open(PROJECT_ROOT / "mcp_config.json", encoding="utf-8") as config_file:
    MCP_SERVERS = [
        str(PROJECT_ROOT / server_path)
        for server_path in json.load(config_file)["mcp_servers"]
    ]

budget = Budget(
    max_iterations=5,       # Allow at most 5 LLM/tool loop iterations.
    max_tokens=4000,        # Limit total token usage for this run.
    max_cost_usd=0.10,      # Cap the estimated model cost at $0.10.
    max_wall_seconds=60,    # Stop the run after 60 seconds.
)

# Build one specialist that aggregates tools from both MCP servers.
research_specialist = Specialist(
    name="research",
    description=(
        "You are a documentation research specialist. Research the "
        "provided task using available tools. Only state facts supported "
        "by tool results. Clearly identify missing information."
    ),
    mcp_servers=MCP_SERVERS,
    budget=budget,
)

# Enable host-level tool decision capture for this run.
os.environ["HOST_TOOL_CAPTURE"] = str(
    PROJECT_ROOT / "host_tool_calls.json"
)

## Ask a question that should require package API and deprecation tools.
result = research_specialist.run(
    "For the create_issue endpoint, explain its API parameters "
    "and whether any fields are deprecated in API version 2025-06-01."
)

# Print the result to inspect which tools the agent used.
print(result)
```

- [ ] **Step 2: Confirm it imports cleanly (no live API calls -- just import + syntax check)**

Run: `python3 -c "import ast; ast.parse(open('test_mcp_research.py').read()); print('syntax ok')"`
Expected: `syntax ok`

(This script makes real Groq + MCP subprocess calls when actually run, same as before this change -- it's a manual one-off script, not part of the automated suite. Running it for real requires `GROQ_API_KEY` set.)

- [ ] **Step 3: Commit**

```bash
git add test_mcp_research.py
git commit -m "Point test_mcp_research.py at the generic Specialist instead of ResearchAgent"
```

---

### Task 6: Point `eval/week10/race.py` at `load_specialists`

**Files:**
- Modify: `eval/week10/race.py:5-16,54-67`

**Interfaces:**
- Consumes: `load_specialists(config_path, budget) -> list[Specialist]` from `agent.specialists` (Task 2); `run_squad(question, specialists, case_id=None)` from `agent.squad` (Task 3).

- [ ] **Step 1: Update imports and add the config path constant**

In `eval/week10/race.py`, change:

```python
from agent.budgets import Budget
from agent.loop import run_agent
from agent.squad import DeprecationWorker, CodeSampleWorker, run_squad
from eval.week7.run_race import grade_entry
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASES_PATH = REPO_ROOT / "eval" / "week8" / "cases.json"
RACE_TABLE_PATH = REPO_ROOT / "race_table.md"
HANDOFFS_LOG_PATH = REPO_ROOT / "handoffs.log"

RACE_BUDGET = Budget(max_iterations=8, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=60.0)
```

to:

```python
from agent.budgets import Budget
from agent.loop import run_agent
from agent.specialists import load_specialists
from agent.squad import run_squad
from eval.week7.run_race import grade_entry
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASES_PATH = REPO_ROOT / "eval" / "week8" / "cases.json"
RACE_TABLE_PATH = REPO_ROOT / "race_table.md"
HANDOFFS_LOG_PATH = REPO_ROOT / "handoffs.log"
SPECIALISTS_CONFIG_PATH = REPO_ROOT / "specialists.json"

RACE_BUDGET = Budget(max_iterations=8, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=60.0)
```

- [ ] **Step 2: Update `run_squad_arm` to build specialists once and reuse them**

Change:

```python
def run_squad_arm(cases: list[dict]) -> list[dict]:
    records = []
    for case in cases:
        dep_worker = DeprecationWorker(RACE_BUDGET)
        code_worker = CodeSampleWorker(RACE_BUDGET)
        result = run_squad(case["question"], dep_worker, code_worker, case_id=case["id"])
        records.append({
            "id": case["id"],
            "passed": grade_entry(result.answer, case),
            "total_tokens": result.total_tokens,
            "total_cost_usd": result.total_cost_usd,
            "wall_seconds": result.wall_seconds,
        })
    return records
```

to:

```python
def run_squad_arm(cases: list[dict]) -> list[dict]:
    records = []
    specialists = load_specialists(SPECIALISTS_CONFIG_PATH, budget=RACE_BUDGET)
    for case in cases:
        result = run_squad(case["question"], specialists, case_id=case["id"])
        records.append({
            "id": case["id"],
            "passed": grade_entry(result.answer, case),
            "total_tokens": result.total_tokens,
            "total_cost_usd": result.total_cost_usd,
            "wall_seconds": result.wall_seconds,
        })
    return records
```

(Specialists are now built once, outside the per-case loop -- each `.run()` call still gets a fresh `BudgetTracker` internally via `run_agent`, so reusing the same `Specialist` instances across cases is safe and avoids re-spawning MCP server subprocesses for every single case.)

- [ ] **Step 3: Confirm the file still parses and references are consistent**

Run: `python3 -c "import ast; ast.parse(open('eval/week10/race.py').read()); print('syntax ok')"`
Expected: `syntax ok`

Run: `grep -n "DeprecationWorker\|CodeSampleWorker" eval/week10/race.py`
Expected: no output (no matches)

- [ ] **Step 4: Commit**

```bash
git add eval/week10/race.py
git commit -m "Point eval/week10/race.py at load_specialists instead of DeprecationWorker/CodeSampleWorker"
```

---

### Task 7: Point `eval/week10/failure_injection.py` at `load_specialists`

**Files:**
- Modify: `eval/week10/failure_injection.py`

**Interfaces:**
- Consumes: `load_specialists(config_path, budget) -> list[Specialist]` from `agent.specialists` (Task 2); `run_squad(question, specialists, case_id=None, force_failure=None)` from `agent.squad` (Task 3).

- [ ] **Step 1: Replace the file's contents**

Replace the entire file `eval/week10/failure_injection.py`:

```python
import json
from pathlib import Path

from agent.budgets import Budget
from agent.specialists import load_specialists
from agent.squad import run_squad

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CASES_PATH = REPO_ROOT / "eval" / "week8" / "cases.json"
FAILURE_CASE_PATH = REPO_ROOT / "failure_case.md"
SPECIALISTS_CONFIG_PATH = REPO_ROOT / "specialists.json"

BUDGET = Budget(max_iterations=8, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=60.0)
TARGET_CASE_ID = "q04"

def main() -> None:
    cases = json.loads(CASES_PATH.read_text())
    case = next(c for c in cases if c["id"] == TARGET_CASE_ID)

    specialists = load_specialists(SPECIALISTS_CONFIG_PATH, budget=BUDGET)

    result = run_squad(
        case["question"],
        specialists,
        case_id=f"{case['id']}-failure-injection",
        force_failure="deprecation_worker",
    )

    dep_hop = next(h for h in result.handoffs if h["hop"] == "orchestrator->deprecation_worker")
    retried = dep_hop["attempts"] > 1

    report = f"""# Failure Case: Injected HTTP 500 on deprecation_worker

## Setup

- Case: `{case['id']}` -- "{case['question']}"
- Injected failure: `deprecation_worker` raises `RuntimeError("HTTP 500: deprecation_worker service unavailable")` on every attempt (simulates the worker's service being down).
- Fact only this worker could normally supply: `{case['expected_fragment']}`

## What the orchestrator actually did

- Attempts made against `deprecation_worker`: {dep_hop['attempts']}
- Error recorded for this hop: `{dep_hop['error']}`
- Resulting task state: `{result.status}`
- Message returned to the user:

> {result.answer}

## Classification

- **Retried:** {"YES -- retried once (per handoffs.log attempts field) before giving up." if retried else "NO -- only one attempt was made."}
- **Task lifecycle outcome:** {"PAUSED: input-required -- the orchestrator stopped and asked the user how to proceed, instead of guessing or quietly degrading." if result.status == "paused_input_required" else "COMPLETED -- the orchestrator returned a final answer despite the failure."}
- **Hallucinated:** NO -- the pause message is a fixed template, not another LLM call, so it cannot state a fact it never confirmed.
"""

    FAILURE_CASE_PATH.write_text(report)
    print(report)
    print(f"wrote {FAILURE_CASE_PATH}")


if __name__ == "__main__":
    main()
```

(`force_failure="deprecation_worker"` still works unchanged because `specialists.json` keeps that exact name -- `_run_specialist_with_retry` now matches it generically against whichever specialist is passed in, not a hardcoded string.)

- [ ] **Step 2: Confirm it parses and no longer references the retired classes**

Run: `python3 -c "import ast; ast.parse(open('eval/week10/failure_injection.py').read()); print('syntax ok')"`
Expected: `syntax ok`

Run: `grep -n "DeprecationWorker\|CodeSampleWorker" eval/week10/failure_injection.py`
Expected: no output (no matches)

- [ ] **Step 3: Commit**

```bash
git add eval/week10/failure_injection.py
git commit -m "Point eval/week10/failure_injection.py at load_specialists"
```

---

### Task 8: Remove dead local-tool exports from `agent/tools.py`

**Files:**
- Modify: `agent/tools.py:143-162`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new -- `TOOL_SCHEMAS`, `TOOL_FUNCTIONS`, `call_tool`, `search_docs`, `get_openapi_spec`, `check_deprecation` are unchanged and remain exported.

- [ ] **Step 1: Confirm nothing still imports the exports about to be removed**

Run: `grep -rn "RESEARCH_TOOL_SCHEMAS\|RESEARCH_TOOL_FUNCTIONS\|PACKAGE_TOOL_SCHEMAS\|PACKAGE_TOOL_FUNCTIONS" --include="*.py" .`
Expected: matches only inside `agent/tools.py` itself (the definitions about to be deleted) -- no other file references them, since Tasks 2-7 already migrated every consumer off them.

- [ ] **Step 2: Delete the dead block**

In `agent/tools.py`, remove everything from the line `# Tools available to the Research Agent` through the end of the file (the `RESEARCH_TOOL_SCHEMAS`, `RESEARCH_TOOL_FUNCTIONS`, `PACKAGE_TOOL_SCHEMAS`, `PACKAGE_TOOL_FUNCTIONS` block), so the file ends with:

```python
def call_tool(name: str, arguments: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return fn(**arguments)
```

- [ ] **Step 3: Confirm the removal is clean**

Run: `grep -n "RESEARCH_TOOL\|PACKAGE_TOOL" agent/tools.py`
Expected: no output (no matches)

- [ ] **Step 4: Run the full suite to confirm nothing depended on the removed exports**

Run: `pytest tests/ -q`
Expected: all PASS, no import errors

- [ ] **Step 5: Commit**

```bash
git add agent/tools.py
git commit -m "Remove dead RESEARCH_TOOL_*/PACKAGE_TOOL_* exports from agent/tools.py"
```

---

### Task 9: Full-suite verification

**Files:** none (verification only)

**Interfaces:** none

- [ ] **Step 1: Run the full automated test suite**

Run: `pytest tests/ -q`
Expected: all PASS, 0 failures, 0 errors

(Scoped to `tests/` deliberately -- root-level `test_mcp_research.py` and `test_recoverable_error.py` are one-off live scripts that make real Groq/MCP calls on import, same as before this change; they are not meant to run under an automated `pytest` invocation from the repo root.)

- [ ] **Step 2: Confirm every retired name is gone from the codebase**

Run: `grep -rn "ResearchAgent\|PackageAgent\|DeprecationWorker\|CodeSampleWorker\|run_orchestrator" --include="*.py" .`
Expected: no output (no matches)

- [ ] **Step 3: Confirm `agent/orchestrator.py` no longer exists**

Run: `test -f agent/orchestrator.py && echo "STILL EXISTS" || echo "deleted"`
Expected: `deleted`

- [ ] **Step 4: Confirm `git status` is clean (everything committed)**

Run: `git status --short`
Expected: no output (clean working tree)

- [ ] **Step 5: Report the final diff summary for human review**

Run: `git log --oneline main..HEAD` (or the appropriate base branch) and `git diff --stat main..HEAD`
Expected: one commit per task above, touching exactly the files listed in each task's **Files** section.
