from agent.loop import run_agent
from agent.budgets import Budget
from agent.config import AGENT_MODEL, price_for
from agent.tools import (
    PACKAGE_TOOL_SCHEMAS,
    PACKAGE_TOOL_FUNCTIONS,
    RESEARCH_TOOL_SCHEMAS,
    RESEARCH_TOOL_FUNCTIONS,
)
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HANDOFFS_LOG_PATH = REPO_ROOT / "handoffs.log"

SYNTHESIS_SYSTEM_PROMPT = (
    "You are the orchestrator for a GitHub API migration assistant team. "
    "You receive a user question plus answers from two specialists: a "
    "deprecation/version specialist and a code-sample specialist. Combine "
    "them into one clear answer. If a specialist reports an error or was "
    "skipped, say plainly that part of the information is unavailable -- "
    "never guess or invent the missing fact to fill the gap."
)

ROUTING_SYSTEM_PROMPT = (
    "You are the routing step of a GitHub API migration assistant team. "
    "There are two specialists available:\n"
    "- deprecation_worker: can ONLY answer by calling two tools -- "
    "get_openapi_spec (returns the exact parameter list for one named "
    "endpoint at one specific API version) and check_deprecation (returns "
    "whether a named endpoint has a deprecated field at one specific API "
    "version, and its replacement). It cannot look up general facts, "
    "limits, scopes, or IDs that are not a parameter name or deprecation "
    "status.\n"
    "- code_sample_worker: searches prose documentation for any other kind "
    "of fact (limits, scopes, IDs, general behavior, how something works) "
    "and writes example code.\n"
    "Route to deprecation_worker only when the question specifically asks "
    "for a parameter name, or whether something is deprecated/what "
    "replaces it, for a named endpoint and/or API version. Route to "
    "code_sample_worker for everything else, even if it names an endpoint "
    "or API version -- naming an endpoint does not by itself mean the "
    "parameter/deprecation tools can answer it.\n"
    "Reply with exactly one word and nothing else: 'deprecation_worker', "
    "'code_sample_worker', or 'both'.\n\n"
    "Examples (illustrations of the pattern only, not real test questions):\n"
    "Q: How do I search issues by label using the GitHub REST API?\n"
    "A: code_sample_worker\n"
    "Q: What is the rate limit for the create_repository endpoint?\n"
    "A: code_sample_worker\n"
    "Q: Is the state_reason field deprecated in API version 2022-11-28?\n"
    "A: deprecation_worker\n"
    "Q: What parameter does create_issue take in API version 2025-06-01 to "
    "assign multiple users?\n"
    "A: deprecation_worker\n"
    "Q: How does the draft field for create_pull_request differ between "
    "API version 2022-11-28 and 2025-06-01, and can you show example "
    "usage?\n"
    "A: both"
)


class DeprecationWorker:
    """Specialist: exact param shapes, deprecation status, version diffs."""

    def __init__(self, budget: Budget):
        self.name = "deprecation_worker"
        self.budget = budget
        self.tool_schemas = PACKAGE_TOOL_SCHEMAS
        self.tool_functions = PACKAGE_TOOL_FUNCTIONS

    def run(self, task: str, client=None):
        return run_agent(
            question=task,
            budget=self.budget,
            client=client,
            system_prompt=(
                "You are the version/deprecation specialist on a GitHub API "
                "migration team. Answer only using get_openapi_spec and "
                "check_deprecation tool results. State exact parameter names "
                "and whether something is deprecated. Never guess a version "
                "fact you did not get from a tool."
            ),
            tool_schemas=self.tool_schemas,
            tool_functions=self.tool_functions,
        )


class CodeSampleWorker:
    """Specialist: prose docs, turned into a short grounded code sample."""

    def __init__(self, budget: Budget):
        self.name = "code_sample_worker"
        self.budget = budget
        self.tool_schemas = RESEARCH_TOOL_SCHEMAS
        self.tool_functions = RESEARCH_TOOL_FUNCTIONS

    def run(self, task: str, client=None):
        return run_agent(
            question=task,
            budget=self.budget,
            client=client,
            system_prompt=(
                "You are the code-sample specialist on a GitHub API "
                "migration team. Use search_docs to find the relevant fact, "
                "then answer with a one- or two-line explanation plus a "
                "short code snippet illustrating it. Only use facts the "
                "tool actually returned."
            ),
            tool_schemas=self.tool_schemas,
            tool_functions=self.tool_functions,
        )


@dataclass
class SquadResult:
    answer: str
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


def _decide_route(question: str, client):
    """Ask the model which specialist(s) this question needs.

    Falls back to calling both if the reply doesn't clearly name either
    worker -- silently answering with zero specialists would be a worse
    failure than occasionally calling one specialist too many.
    """
    choice, tokens, cost = _call_llm(client, ROUTING_SYSTEM_PROMPT, question)
    normalized = (choice or "").strip().lower()

    call_dep = "both" in normalized or "deprecation_worker" in normalized
    call_code = "both" in normalized or "code_sample_worker" in normalized
    if not call_dep and not call_code:
        call_dep = call_code = True

    return call_dep, call_code, normalized, tokens, cost


def run_squad(
    question: str,
    deprecation_worker: DeprecationWorker,
    code_sample_worker: CodeSampleWorker,
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
    call_dep, call_code, route_choice, route_tokens, route_cost = _decide_route(question, client)
    handoffs.append({
        "case_id": case_id,
        "hop": "orchestrator->routing_decision",
        "status": "ok",
        "decision": route_choice,
        "tokens": route_tokens,
    })
    total_tokens += route_tokens
    total_cost += route_cost

    # --- Hop 1: deprecation_worker (only if routed there), with one retry ---
    dep_text = "[skipped by router: question judged not to need the deprecation/version specialist]"
    if call_dep:
        dep_result = None
        dep_error = None
        attempts = 0
        while attempts < 2 and dep_result is None:
            attempts += 1
            try:
                if force_failure == "deprecation_worker":
                    raise RuntimeError("HTTP 500: deprecation_worker service unavailable")
                dep_result = deprecation_worker.run(question, client=client)
            except Exception as exc:
                dep_error = str(exc)

        handoffs.append({
            "case_id": case_id,
            "hop": "orchestrator->deprecation_worker",
            "status": "ok" if dep_result else "error",
            "error": dep_error if not dep_result else None,
            "attempts": attempts,
            "tokens": dep_result.total_tokens if dep_result else 0,
        })
        if dep_result:
            total_tokens += dep_result.total_tokens
            total_cost += dep_result.total_cost_usd
            dep_text = dep_result.answer
        else:
            dep_text = f"[ERROR] {dep_error}"
    else:
        handoffs.append({
            "case_id": case_id,
            "hop": "orchestrator->deprecation_worker",
            "status": "skipped",
            "tokens": 0,
        })

    # --- Hop 2: code_sample_worker (only if routed there) ---
    code_text = "[skipped by router: question judged not to need the code-sample specialist]"
    if call_code:
        code_result = code_sample_worker.run(question, client=client)
        handoffs.append({
            "case_id": case_id,
            "hop": "orchestrator->code_sample_worker",
            "status": "ok",
            "tokens": code_result.total_tokens,
        })
        total_tokens += code_result.total_tokens
        total_cost += code_result.total_cost_usd
        code_text = code_result.answer
    else:
        handoffs.append({
            "case_id": case_id,
            "hop": "orchestrator->code_sample_worker",
            "status": "skipped",
            "tokens": 0,
        })

    # --- Hop 3: synthesis call (re-sends whatever the called workers said) ---
    synthesis_prompt = (
        f"User question: {question}\n\n"
        f"Deprecation/version specialist answer:\n{dep_text}\n\n"
        f"Code-sample specialist answer:\n{code_text}\n\n"
        "Combine these into one answer for the user."
    )
    final_answer, synth_tokens, synth_cost = _call_llm(client, SYNTHESIS_SYSTEM_PROMPT, synthesis_prompt)

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
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        wall_seconds=time.monotonic() - start,
        handoffs=handoffs,
    )
