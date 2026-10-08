# Generic MCP-Backed Specialist Squad

Status: approved by user (2026-10-08), pending spec self-review

## 1. Goal

Replace today's duplicated, asymmetric multi-agent setup with one
config-driven squad where every specialist sources its tools dynamically
from MCP (not local Python function calling), routing and failure handling
work uniformly across however many specialists are configured, and the two
existing orchestration entry points collapse into one.

### Problems this fixes

- `DeprecationWorker`/`CodeSampleWorker` (`agent/squad.py`) call local
  functions in `agent/tools.py` directly, even though MCP servers already
  exist for the same data (`agent/mcp_servers/docs_server.py`,
  `package_server.py`) and are already used by a separate, unintegrated
  `ResearchAgent` (`agent/specialists.py`).
- `run_squad`'s retry + pause-on-failure handling exists only for
  `deprecation_worker`; `code_sample_worker` has no retry and an uncaught
  exception there crashes the whole run.
- `run_orchestrator` (`agent/orchestrator.py`) is a second, simpler,
  no-routing, no-error-handling orchestration primitive that nothing in
  the real eval/race pipeline actually uses — only exercised via mocks in
  `tests/test_multiagent.py`.
- Adding a specialist today means writing a new class and hand-editing the
  two-name routing prompt.

## 2. Specialist definition — `specialists.json`

New file, sibling to `mcp_config.json`, same "config describes it, code
discovers dynamically" spirit:

```json
{
  "specialists": [
    {
      "name": "deprecation_worker",
      "description": "Exact parameter shapes, deprecation status, and version diffs for one named GitHub endpoint and API version.",
      "mcp_servers": ["agent/mcp_servers/package_server.py"]
    },
    {
      "name": "code_sample_worker",
      "description": "Prose documentation search for any other kind of fact (limits, scopes, IDs, general behavior), turned into a short grounded code sample.",
      "mcp_servers": ["agent/mcp_servers/docs_server.py"]
    }
  ]
}
```

`description` is used twice: shown to whoever edits the config, and fed
verbatim into the routing prompt (section 4). A specialist's
`mcp_servers` list may name one server (today's two workers) or several
(today's `ResearchAgent` pattern of aggregating multiple servers into one
agent) — the mechanism doesn't care, which is what lets `ResearchAgent`'s
capability fold into this same shape instead of staying a separate class.

## 3. `Specialist` class (replaces `ResearchAgent`, `PackageAgent`,
`DeprecationWorker`, `CodeSampleWorker`)

Lives in `agent/specialists.py`, replacing its current contents entirely.

```python
class Specialist:
    def __init__(self, name: str, description: str, mcp_servers: list[str], budget: Budget):
        self.name = name
        self.budget = budget
        self.tool_schemas, self.tool_functions = build_multi_mcp_tool_registry(mcp_servers)
        grounding = (
            f"The only tools available to you are: {', '.join(self.tool_functions)}. "
            "Use only these -- never invent a tool name."
        )
        self.system_prompt = f"{description}\n\n{grounding}"

    def run(self, task: str, client=None):
        return run_agent(
            question=task, budget=self.budget, client=client,
            system_prompt=self.system_prompt,
            tool_schemas=self.tool_schemas, tool_functions=self.tool_functions,
        )
```

Construction (and MCP discovery) happens once per `Specialist`, same
lifetime as today's classes — not per-question.

## 4. Routing — generalized over N specialists

`ROUTING_SYSTEM_PROMPT` becomes a function of the configured specialist
list instead of a static string naming two workers:

```python
def build_routing_prompt(specialists: list[Specialist]) -> str:
    roster = "\n".join(f"- {s.name}: {s.description_text}" for s in specialists)
    # ... instructs the model to reply with the names of every specialist
    # that applies, comma-separated, or "none" -- "none" is treated the
    # same as today's ambiguous-reply fallback: route to all of them.
```

`_decide_route` generalizes from two boolean flags (`call_dep`,
`call_code`) to a `set[str]` of specialist names to call, parsed from the
LLM's reply by checking which configured names appear in it. Unparseable
or empty replies fall back to "route to all" — same fail-open reasoning
`_decide_route` already uses today, just no longer hardcoded to exactly
two names.

## 5. Execution — shared retry wrapper, sequential

```python
def _run_specialist_with_retry(specialist, question, client, max_attempts=2):
    # identical to today's deprecation_worker-only loop, generalized:
    # returns (result_or_None, error_or_None, attempts_made)
```

Routed specialists run **sequentially** (not parallel — nothing in this
codebase is built or tested for concurrent MCP subprocess calls or
concurrent `handoffs.log` writes; parallelizing is a future optimization,
not in scope here). Every routed specialist gets this same wrapper — this
is what removes the `deprecation_worker`-only asymmetry. Each call is
logged to `handoffs.log` as `{"hop": f"orchestrator->{specialist.name}", "status": "ok"|"error"|"skipped", "attempts": N, "tokens": ...}`,
same schema as today, just not limited to two hop names.

`force_failure` (the test hook used by `eval/week10/failure_injection.py`)
generalizes from `force_failure == "deprecation_worker"` to matching
against any configured specialist's `name` — failure injection works
against whichever specialist a test names.

## 6. Partial-failure synthesis and pause semantics

After execution, each specialist is in one of three states: `ok`,
`error`, `skipped` (not routed).

- **If every routed specialist is `error`** (none succeeded): skip
  synthesis entirely and return today's fixed-template
  `paused_input_required` message (not another LLM call — this is what
  guarantees the pause message itself can't hallucinate). This is
  structurally enforced, not just a prompt instruction: the code path to
  the synthesis call is skipped, so a test can assert the synthesis LLM
  call was never made in this branch.
- **Otherwise** (at least one `ok`): run synthesis with every `ok`
  specialist's answer included, plus one explicit line per `error`/
  `skipped` specialist naming it and why it's missing. Return
  `status="completed"` even though some specialists failed — this is the
  behavior change from today (today, only `deprecation_worker` failing
  pauses the whole run; now, any individual failure degrades gracefully
  as long as something else came back).

This generalizes today's exact two-worker logic (`dep_result is None` →
pause) to "all routed results are None → pause," which collapses to
identical behavior when there are only two specialists and both are
routed — so this isn't a behavior change for today's two-worker case, only
for configurations with more specialists.

## 7. Deleted / rewritten / new / unaffected files

**Deleted:**
- `agent/orchestrator.py` — `run_orchestrator` retired; the one remaining
  orchestrator's only job is routing (confirmed by user: "orchestrator
  only need to choose based on question user asked where it will lead
  to").

**Rewritten:**
- `agent/specialists.py` — `ResearchAgent`/`PackageAgent` classes removed;
  replaced by the generic `Specialist` class (section 3).
- `agent/squad.py` — `DeprecationWorker`/`CodeSampleWorker` classes
  removed; `run_squad` rewritten to load a specialist list and run the
  generalized routing/execution/synthesis flow (sections 4-6).
  `SquadResult`, `_append_handoff`, `_call_llm` are unchanged — their shape
  never depended on there being exactly two workers.
- `agent/tools.py` — delete `RESEARCH_TOOL_SCHEMAS`, `RESEARCH_TOOL_FUNCTIONS`,
  `PACKAGE_TOOL_SCHEMAS`, `PACKAGE_TOOL_FUNCTIONS` (only consumers were the
  retired classes). Keep `search_docs`, `get_openapi_spec`,
  `check_deprecation` (still back the MCP servers) and keep
  `TOOL_SCHEMAS`/`TOOL_FUNCTIONS`/`call_tool` untouched (these back
  `agent/loop.py`'s single-agent default path — the "Single Agent" race
  baseline — which is unrelated to the squad redesign).

**New:**
- `specialists.json` (section 2).

**Unaffected (confirmed, not touched):**
- `agent/mcp_adapter.py`, `agent/loop.py`, `agent/mcp_servers/*.py` —
  already correctly generic; nothing about this redesign requires
  changing tool discovery or the ReAct loop itself.
- `mcp_config.json` — independently read by `generate_tool_count_report.py`;
  no ownership conflict with `specialists.json` (the latter's
  `mcp_servers` entries just point at the same server file paths).
- `capture_error_transcript.py` — standalone one-off debug script calling
  `build_mcp_tool_registry` directly; doesn't reference any retired class.

**Updated call sites:**
- `test_mcp_research.py` — swap `ResearchAgent(mcp_server_scripts=...)`
  for building a `Specialist` from a `specialists.json` entry.
- `eval/week10/race.py`, `eval/week10/failure_injection.py` — swap
  `DeprecationWorker(...)`/`CodeSampleWorker(...)` construction for
  loading specialists from `specialists.json`.

## 8. Testing

**Deleted** (target no longer exists): `tests/test_multiagent.py`'s three
`run_orchestrator` tests, plus `test_research_agent_uses_existing_agent_loop`,
`test_research_agent_only_receives_research_tools`,
`test_package_agent_only_receives_package_tools`.

**Rewritten, same intent:** the "only receives its own tools" assertions
become one test against `Specialist`, built from a config entry pointing
at a mocked `build_multi_mcp_tool_registry`, asserting `tool_functions`
contains only that server's tools and `system_prompt` contains the
grounding line with those exact names.

**New:**
- Routing builds its prompt correctly for 1, 2, and 4+ configured
  specialists, and parses a multi-name response.
- Partial-failure synthesis: 2 of 3 routed `ok`, 1 `error` →
  `status="completed"`, synthesis prompt names the failed one.
- All-routed-failed: every routed specialist `error` →
  `status="paused_input_required"`, and the synthesis LLM call is
  asserted to never have been made.
- The shared retry wrapper, tested once generically (attempt counts,
  `handoffs.log` shape) instead of only through `deprecation_worker`.

**MCP discovery in tests:** construction-level tests mock
`build_multi_mcp_tool_registry` (no real subprocess spawn), consistent
with how existing tests already mock `run_agent`/`.run` rather than
hitting Groq. Real end-to-end MCP round-trips stay covered the way
`test_mcp_research.py` already does it, now exercising `Specialist`/
`run_squad` instead of `ResearchAgent`.

## 9. Out of scope (this pass)

- Parallel execution of routed specialists (sequential only, per
  decision in section 5).
- A "critical specialist" concept where some failures pause and others
  don't (rejected in favor of uniform "pause only if all failed").
- Changing the retry attempt count (kept at today's 2 attempts / 1 retry).
- Any change to `mcp_config.json`'s role or `agent/mcp_adapter.py`'s
  per-call subprocess-spawn behavior.
