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
