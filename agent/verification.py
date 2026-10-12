"""Independent checks on specialist output, separate from the model that
produced it. The deterministic check never trusts the specialist's own
claims: it looks at the recorded tool-call evidence."""

import re


def verify_specialist_result(result) -> tuple[bool, str | None]:
    """Return (accepted, reason_if_rejected).

    Rejects a run that was cut off by its budget, produced no answer, or
    produced an answer without a single successful tool call behind it.
    Objects that carry no tool-call record (non-agent fakes) are accepted
    on the answer check alone because they cannot be audited.
    """
    if getattr(result, "terminated_by_budget", False):
        return False, f"specialist stopped by budget: {getattr(result, 'budget_reason', None)}"
    answer = getattr(result, "answer", None)
    if answer is None or not str(answer).strip():
        return False, "specialist returned no answer"

    calls = getattr(result, "tool_calls", None)
    if calls is None:
        return True, None
    if not any(c["status"] == "ok" for c in calls):
        errors = "; ".join(
            f"{c['tool']}: {c['result_excerpt'][:200]}" for c in calls if c["status"] == "error"
        )
        return False, "answer has no successful tool evidence" + (f" ({errors})" if errors else " (no tools were called)")
    return True, None


def format_evidence(calls: list[dict] | None) -> str:
    if not calls:
        return "(no tool calls)"
    return "\n".join(
        f"- {c['tool']}({c['arguments']}) -> {c['status']}: {c['result_excerpt'][:300]}" for c in calls
    )


VERIFIER_SYSTEM_PROMPT = (
    "You are an independent fact-checker. Given a user question, the tool "
    "evidence that was actually gathered, and a drafted final answer, decide "
    "whether the answer (1) addresses the question and (2) states nothing "
    "that the evidence does not support. Reply with exactly 'SUPPORTED' or "
    "'UNSUPPORTED: <one-sentence reason>'."
)


def parse_verdict(text: str | None) -> tuple[bool, str]:
    text = (text or "").strip()
    if re.match(r"^SUPPORTED\b", text, re.IGNORECASE):
        return True, text
    return False, text or "verifier returned no verdict"


_FENCED = re.compile(r"```.*?```", re.DOTALL)
_CLAIM_PATTERNS = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),          # API versions / dates
    re.compile(r"`([^`\n]{2,80})`"),                   # inline code identifiers
    re.compile(r"(?<![\w/])(/[a-z0-9_{}/.-]{3,})"),    # URL paths such as /repos/{owner}/{repo}/issues
)


def ungrounded_claims(answer: str, question: str, evidence: dict) -> list[str]:
    """Deterministic grounding check on the final answer.

    Extracts concrete, checkable claims -- dates/versions, inline-code
    identifiers and URL paths (code blocks are skipped) -- and returns those
    that appear neither in the user's question nor in any tool result.
    Conservative by design: it catches invented specifics, not paraphrase.
    """
    haystack = question + "\n" + "\n".join(
        c.get("result") or c.get("result_excerpt", "")
        for calls in evidence.values() for c in (calls or []) if c["status"] == "ok"
    )
    prose = _FENCED.sub(" ", answer or "")
    claims = []
    for pattern in _CLAIM_PATTERNS:
        for m in pattern.finditer(prose):
            claim = (m.group(1) if pattern.groups else m.group(0)).strip()
            present = re.search(rf"(?<![\w-]){re.escape(claim)}(?![\w-])", haystack)
            if claim and not present and claim not in claims:
                claims.append(claim)
    return claims


def evidence_footer(evidence: dict) -> str:
    """Human-readable list of the successful tool calls behind an answer."""
    lines = []
    for name, calls in evidence.items():
        for c in calls or []:
            if c["status"] != "ok":
                continue
            args = ", ".join(f"{k}={v}" for k, v in c["arguments"].items())
            lines.append(f"- {name}: {c['tool']}({args})")
    return ("\n\nEvidence (tool calls):\n" + "\n".join(lines)) if lines else ""


def plan_warnings(plan: dict, routed: list[str]) -> list[str]:
    """Problems in the router's plan that the executor silently works around."""
    warnings = []
    for name, entry in plan.items():
        for dep in entry["after"]:
            if dep not in routed:
                warnings.append(f"{name} depends on {dep}, which was not routed; dependency dropped")
    state = {}

    def visit(n, stack):
        if state.get(n) == "done":
            return
        if n in stack:
            warnings.append("dependency cycle: " + " -> ".join(stack[stack.index(n):] + [n]))
            return
        for d in plan.get(n, {}).get("after", []):
            if d in plan:
                visit(d, stack + [n])
        state[n] = "done"

    for n in plan:
        visit(n, [])
    return warnings
