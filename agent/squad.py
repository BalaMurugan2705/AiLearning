import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent.config import AGENT_MODEL, price_for
from agent.errors import NonRetryableError
from agent.specialists import Specialist
from agent.verification import (
    VERIFIER_SYSTEM_PROMPT,
    evidence_footer,
    format_evidence,
    parse_verdict,
    plan_warnings,
    ungrounded_claims,
    verify_specialist_result,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HANDOFFS_LOG_PATH = REPO_ROOT / "handoffs.log"

SYNTHESIS_SYSTEM_PROMPT = (
    "You are the orchestrator for a team of specialist assistants. "
    "You receive a user question plus answers from however many "
    "specialists were routed to it. Combine them into one clear answer. "
    "If a specialist's answer is marked as skipped or failed, say plainly "
    "that part of the information is unavailable -- never guess or invent "
    "the missing fact to fill the gap."
)


def build_routing_prompt(specialists: list[Specialist]) -> str:
    """Build the routing prompt from whatever specialists are configured,
    instead of a static prompt hardcoded to two named workers."""

    def _line(s):
        tools = getattr(s, "tool_names", None)
        suffix = f" (discovered tools: {', '.join(tools)})" if tools else ""
        return f"- {s.name}: {s.description}{suffix}"

    roster = "\n".join(_line(s) for s in specialists)
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
        "guessing none.\n\n"
        "Optionally, give each specialist a focused sub-task, one per line, "
        "as 'name: sub-task'. If a specialist needs another specialist's "
        "result first, write 'name (after other_name): sub-task'; "
        "otherwise specialists run independently."
    )


@dataclass
class SquadResult:
    answer: str
    status: str  # "completed" or "paused_input_required"
    total_tokens: int
    total_cost_usd: float
    wall_seconds: float
    handoffs: list[dict] = field(default_factory=list)
    # Per-specialist tool-call evidence: {specialist_name: [call dicts]}.
    evidence: dict = field(default_factory=dict)
    # Result of the optional LLM verification pass (None when not run).
    verification: dict | None = None


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


_PLAN_LINE = re.compile(
    r"^\s*(?:[-*\d.)]+\s*)?([A-Za-z0-9_]+)\s*(?:\(\s*after\s+([^)]*)\))?\s*:\s*(\S.*)$"
)


def parse_plan(text: str | None, specialists) -> dict:
    """Parse optional 'name: sub-task' / 'name (after a, b): sub-task' lines.

    Returns {name: {"task": str, "after": [names]}} for lines naming a
    configured specialist; {} when the reply is a bare name list. Unknown
    dependency names are ignored.
    """
    valid = {s.name.lower(): s.name for s in specialists}
    plan = {}
    for line in (text or "").splitlines():
        m = _PLAN_LINE.match(line)
        if not m or m.group(1).lower() not in valid:
            continue
        name = valid[m.group(1).lower()]
        deps = [
            valid[d.strip().lower()]
            for d in (m.group(2) or "").split(",")
            if d.strip().lower() in valid and valid[d.strip().lower()] != name
        ]
        plan[name] = {"task": m.group(3).strip(), "after": deps}
    return plan


def order_by_dependencies(names: list[str], plan: dict) -> list[str]:
    """Order routed specialists so each runs after the ones it depends on.
    Dependencies on specialists that were not routed are dropped; a cycle
    falls back to the original order for the remaining names."""
    remaining = list(names)
    ordered: list[str] = []
    while remaining:
        ready = [
            n for n in remaining
            if all(d in ordered or d not in names for d in plan.get(n, {}).get("after", []))
        ]
        if not ready:
            ready = [remaining[0]]  # cycle: break it deterministically
        ordered.append(ready[0])
        remaining.remove(ready[0])
    return ordered


def _decide_route_with_plan(question: str, specialists: list[Specialist], client):
    """Ask the model which specialist(s) this question needs, and optionally
    what each should do and in what order.

    Falls back to calling every specialist if the reply doesn't clearly
    name any of them -- silently answering with zero specialists would be
    a worse failure than occasionally calling one too many.
    """
    routing_prompt = build_routing_prompt(specialists)
    choice, tokens, cost = _call_llm(client, routing_prompt, question)
    normalized = (choice or "").strip().lower()

    plan = parse_plan(choice, specialists)
    if plan:
        matched = set(plan)
    else:
        valid_names = {s.name for s in specialists}
        matched = {
            name for name in valid_names
            if re.search(rf"\b{re.escape(name.lower())}\b", normalized)
        }
        if not matched:
            matched = set(valid_names)

    return matched, normalized, tokens, cost, plan


def _decide_route(question: str, specialists: list[Specialist], client):
    matched, normalized, tokens, cost, _plan = _decide_route_with_plan(question, specialists, client)
    return matched, normalized, tokens, cost


def _build_task(question: str, name: str, plan: dict, finished: dict) -> str:
    """The task a specialist receives: its sub-task (or the raw question),
    plus the results of any specialists it depends on."""
    entry = plan.get(name)
    task = question if not entry else f"{entry['task']}\n\n(Original user question: {question})"
    context = []
    for dep in (entry or {}).get("after", []):
        outcome = finished.get(dep)
        if outcome is None or outcome["status"] == "skipped":
            continue
        if outcome["status"] == "ok":
            context.append(f"{dep} result:\n{outcome['answer']}")
        else:
            context.append(f"{dep} FAILED ({outcome['error']}); do not assume its result.")
    if context:
        task += "\n\nResults from specialists that ran before you:\n" + "\n\n".join(context)
    return task


def _run_specialist_with_retry(
    specialist: Specialist,
    question: str,
    client,
    fault_hook=None,
    max_attempts: int = 2,
    backoff_seconds: float = 0.5,
    sleep=time.sleep,
):
    """Run one specialist with up to max_attempts tries.

    Returns (result_or_None, error_or_None, attempts_made). A result only
    counts as success if it passes verify_specialist_result (not budget-cut,
    has an answer, backed by at least one successful tool call). Policy and
    consent failures are not retried. fault_hook(specialist), if given, is
    called before each attempt and may raise to inject a failure.
    """
    result = None
    error = None
    attempts = 0
    while attempts < max_attempts and result is None:
        attempts += 1
        try:
            if fault_hook is not None:
                fault_hook(specialist)
            candidate = specialist.run(question, client=client)
            accepted, reason = verify_specialist_result(candidate)
            if accepted:
                result = candidate
            else:
                error = reason
        except NonRetryableError as exc:
            return None, str(exc), attempts
        except Exception as exc:
            error = str(exc)
        if result is None and attempts < max_attempts and backoff_seconds:
            sleep(backoff_seconds * attempts)
    return result, error, attempts


def run_squad(
    question: str,
    specialists: list[Specialist],
    client=None,
    case_id: str | None = None,
    fault_hook=None,
    verify_with_llm: bool = False,
    evidence_in_answer: bool = True,
) -> SquadResult:
    if client is None:
        from groq import Groq
        client = Groq()

    start = time.monotonic()
    total_tokens = 0
    total_cost = 0.0
    handoffs = []

    # --- Hop 0: routing decision ---
    routed_names, route_choice, route_tokens, route_cost, plan = _decide_route_with_plan(
        question, specialists, client
    )
    handoffs.append({
        "case_id": case_id,
        "hop": "orchestrator->routing_decision",
        "status": "ok",
        "decision": route_choice,
        "plan": plan,
        "plan_warnings": plan_warnings(plan, sorted(routed_names)),
        "tokens": route_tokens,
    })
    total_tokens += route_tokens
    total_cost += route_cost

    # --- Skipped specialists are logged; routed ones run in dependency order ---
    finished: dict[str, dict] = {}
    for specialist in specialists:
        if specialist.name not in routed_names:
            handoffs.append({
                "case_id": case_id,
                "hop": f"orchestrator->{specialist.name}",
                "status": "skipped",
                "tokens": 0,
            })
            finished[specialist.name] = {"name": specialist.name, "status": "skipped", "answer": None, "error": None}

    by_name = {s.name: s for s in specialists}
    routed_in_order = order_by_dependencies([s.name for s in specialists if s.name in routed_names], plan)
    for name in routed_in_order:
        specialist = by_name[name]
        task = _build_task(question, name, plan, finished)
        result, error, attempts = _run_specialist_with_retry(
            specialist, task, client, fault_hook=fault_hook,
        )
        handoffs.append({
            "case_id": case_id,
            "hop": f"orchestrator->{specialist.name}",
            "status": "ok" if result else "error",
            "error": error if not result else None,
            "attempts": attempts,
            "tokens": result.total_tokens if result else 0,
            "tool_calls": [
                {"tool": c["tool"], "status": c["status"]} for c in getattr(result, "tool_calls", None) or []
            ],
        })

        if result:
            total_tokens += result.total_tokens
            total_cost += result.total_cost_usd
            finished[name] = {
                "name": name, "status": "ok", "answer": result.answer, "error": None,
                "evidence": getattr(result, "tool_calls", None),
            }
        else:
            finished[name] = {"name": name, "status": "error", "answer": None, "error": error}

    outcomes = [finished[s.name] for s in specialists]

    # --- Pause only if every routed specialist failed ---
    routed_outcomes = [o for o in outcomes if o["status"] != "skipped"]
    if routed_outcomes and all(o["status"] == "error" for o in routed_outcomes):
        for entry in handoffs:
            _append_handoff(entry)
        failed_names = ", ".join(o["name"] for o in routed_outcomes)
        pause_message = (
            "I can't confirm this from any of the routed specialists right "
            f"now ({failed_names}): "
            + "; ".join(f"{o['name']}: {o['error']}" for o in routed_outcomes)
            + ". Do you want me to wait and try again "
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
            answer_sections.append(
                f"{outcome['name']} answer:\n{outcome['answer']}\n"
                f"{outcome['name']} tool evidence:\n{format_evidence(outcome.get('evidence'))}"
            )
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

    evidence = {o["name"]: o["evidence"] for o in outcomes if o["status"] == "ok" and o.get("evidence") is not None}

    verification = None

    # Deterministic grounding: concrete claims in the answer (dates, inline
    # identifiers, URL paths) must appear in the question or a tool result.
    if evidence:
        ungrounded = ungrounded_claims(final_answer, question, evidence)
        verification = {"method": "deterministic", "supported": not ungrounded, "ungrounded_claims": ungrounded}
        if ungrounded:
            final_answer = (
                "[Unverified: these specifics were not found in the tool evidence: "
                + ", ".join(ungrounded) + "]\n\n" + final_answer
            )
        handoffs.append({
            "case_id": case_id, "hop": "orchestrator->grounding_check",
            "status": "ok" if not ungrounded else "ungrounded", "tokens": 0,
        })

    if verify_with_llm:
        evidence_text = "\n\n".join(f"{n}:\n{format_evidence(c)}" for n, c in evidence.items())
        verdict_text, v_tokens, v_cost = _call_llm(
            client, VERIFIER_SYSTEM_PROMPT,
            f"Question: {question}\n\nEvidence:\n{evidence_text or '(none)'}\n\nDrafted answer:\n{final_answer}",
        )
        supported, detail = parse_verdict(verdict_text)
        verification = {**(verification or {}), "method": "llm" if not verification else "deterministic+llm",
                        "supported": supported and (verification or {}).get("supported", True),
                        "detail": detail}
        total_tokens += v_tokens
        total_cost += v_cost
        handoffs.append({
            "case_id": case_id, "hop": "orchestrator->verification",
            "status": "ok" if supported else "unsupported", "tokens": v_tokens,
        })
        if not supported:
            final_answer = f"[Unverified: {detail}]\n\n{final_answer}"

    if evidence_in_answer:
        final_answer += evidence_footer(evidence)

    for entry in handoffs:
        _append_handoff(entry)

    return SquadResult(
        answer=final_answer,
        status="completed",
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        wall_seconds=time.monotonic() - start,
        handoffs=handoffs,
        evidence=evidence,
        verification=verification,
    )
