import json
import time
from dataclasses import dataclass, field

from agent.budgets import Budget, BudgetExceeded, BudgetTracker
from agent.config import AGENT_MODEL, price_for
from agent.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, call_tool
# Import os to read the optional host-level capture file path.
import os

# Import datetime to timestamp the model's tool-selection events.
from datetime import datetime, timezone
# Mitigation for the "hallucinated_tool" / "api_error" failure mode found by
# eval/week8/trajectory_eval.py: this model, on Groq, occasionally (a)
# invents a tool name that was never in TOOL_SCHEMAS (e.g. "open_file"
# instead of search_docs), or (b) emits raw reasoning prose that Groq can't
# parse as a turn at all. Both surface as the *entire* .create() call being
# rejected with a 400 before any message ever reaches this loop -- previously
# an unhandled exception that lost the whole run for one bad generation.
# Re-planning: tell the model what went wrong and which tools actually
# exist, then let it try again, instead of crashing.
_RECOVERABLE_ERROR_SUBSTRINGS = ("tool call validation failed", "output_parse_failed")


def _is_recoverable_turn_error(exc: Exception) -> bool:
    return any(s in str(exc) for s in _RECOVERABLE_ERROR_SUBSTRINGS)
def _record_host_tool_event(event: dict) -> None:
    """Record an LLM host tool-selection or execution event when enabled."""

    # Read the optional output path; without it, normal agent runs are unchanged.
    output_path = os.getenv("HOST_TOOL_CAPTURE")
    if not output_path:
        return

    # Load previous events so multiple tool calls are retained in one JSON array.
    try:
        with open(output_path, "r", encoding="utf-8") as file:
            events = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        # Start a fresh capture when the file is missing or unreadable.
        events = []

    # Add a timestamp so the host events can be correlated with wire.json.
    event["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Append the new event to the existing capture.
    events.append(event)

    # Rewrite the JSON file with the complete event history.
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(events, file, indent=2)
SYSTEM_PROMPT = (
    "You help developers migrate code between GitHub API versions. You have "
    "tools to search documentation, look up exact endpoint parameter shapes, "
    "and check whether something is deprecated. Only state facts a tool call "
    "returned to you -- never guess a parameter name, default, or deprecation "
    "status. When you have enough information, answer the question directly "
    "in plain text with no further tool calls."
)

@dataclass
class RunResult:
    answer: str | None
    terminated_by_budget: bool
    budget_reason: str | None
    iterations: int
    total_tokens: int
    total_cost_usd: float
    wall_seconds: float
    transcript: list[dict] = field(default_factory=list)
    # Evidence of what each tool call did: name, arguments, ok/error, excerpt.
    tool_calls: list[dict] = field(default_factory=list)


_EXCERPT_CHARS = 600
_FULL_RESULT_CHARS = 20_000


def _tool_status(result: str) -> str:
    """A tool result is an error if the host/adapter flagged it, or if the
    tool itself reported an application-level error inside its content
    (e.g. {"error": "No spec for ..."}), which is not usable evidence."""
    try:
        parsed = json.loads(result)
    except (TypeError, ValueError):
        return "ok"
    if not isinstance(parsed, dict):
        return "ok"
    if "content" not in parsed:
        return "error" if parsed.get("error") else "ok"
    for item in parsed["content"] if isinstance(parsed["content"], list) else []:
        try:
            inner = json.loads(item) if isinstance(item, str) else item
        except ValueError:
            continue
        if isinstance(inner, dict) and inner.get("error"):
            return "error"
    return "ok"


def _budget_result(tracker: BudgetTracker, reason: str, transcript: list[dict], tool_calls: list[dict]) -> RunResult:
    return RunResult(
        answer=None,
        terminated_by_budget=True,
        budget_reason=reason,
        iterations=tracker.iterations,
        total_tokens=tracker.total_tokens,
        total_cost_usd=tracker.total_cost_usd,
        wall_seconds=tracker.elapsed(),
        transcript=transcript,
        tool_calls=tool_calls,
    )

def run_agent(
    question: str,
    budget: Budget,
    client=None,
    system_prompt: str | None = None,
    tool_schemas: list | None = None,
    tool_functions: dict | None = None,
) -> RunResult:
    if client is None:
        from groq import Groq

        client = Groq()

    tracker = BudgetTracker(budget=budget)
    effective_system_prompt = system_prompt or SYSTEM_PROMPT
    effective_tool_schemas = (
        tool_schemas if tool_schemas is not None else TOOL_SCHEMAS
    )

    effective_tool_functions = (
        tool_functions if tool_functions is not None else TOOL_FUNCTIONS
    )

    messages = [
    {"role": "system", "content": effective_system_prompt},
    {"role": "user", "content": question}, 
]
    transcript = [dict(m) for m in messages]
    tool_calls: list[dict] = []
    call_cache: dict[str, str] = {}

    while True:
        try:
            tracker.start_iteration()
        except BudgetExceeded as exc:
            return _budget_result(tracker, exc.reason, transcript, tool_calls)

        try:
            response = client.chat.completions.create(
                model=AGENT_MODEL, messages=messages, tools=effective_tool_schemas, tool_choice="auto"
            )
        except Exception as exc:
            if not _is_recoverable_turn_error(exc):
                raise
            correction = {
                "role": "user",
                "content": (
                    f"Your last turn could not be used ({exc}). The only tools "
                    f"that exist are: {', '.join(effective_tool_functions)}. "
                    "Call one of them by its exact name, or answer in plain "
                    "text with no tool call."
                ),
            }
            messages.append(correction)
            transcript.append(correction)
            continue

        usage = response.usage
        price_in, price_out = price_for(AGENT_MODEL)
        try:
            tracker.record_usage(usage.prompt_tokens, usage.completion_tokens, price_in, price_out)
        except BudgetExceeded as exc:
            return _budget_result(tracker, exc.reason, transcript, tool_calls)

        message = response.choices[0].message
        requested_calls = getattr(message, "tool_calls", None)

        if not requested_calls:
            transcript.append({"role": "assistant", "content": message.content})
            return RunResult(
                answer=message.content,
                terminated_by_budget=False,
                budget_reason=None,
                iterations=tracker.iterations,
                total_tokens=tracker.total_tokens,
                total_cost_usd=tracker.total_cost_usd,
                wall_seconds=tracker.elapsed(),
                transcript=transcript,
                tool_calls=tool_calls,
            )

        assistant_msg = {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in requested_calls
            ],
        }
        messages.append(assistant_msg)
        transcript.append(assistant_msg)

        for tc in requested_calls:
            name = tc.function.name
            fn = effective_tool_functions.get(name)

            # Malformed arguments become a tool error the model can correct,
            # instead of crashing the whole run.
            try:
                args = json.loads(tc.function.arguments)
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
                parse_error = None
            except ValueError as exc:
                args, parse_error = {}, str(exc)

            # Record the model's decision separately from MCP wire traffic.
            _record_host_tool_event({
                "event": "llm_tool_selected",
                "tool_call_id": tc.id,
                "tool_name": name,
                "arguments": args,
                "execution_status": "pending",
            })

            cache_key = f"{name}:{json.dumps(args, sort_keys=True)}"
            if parse_error is not None:
                result = json.dumps({
                    "error": "invalid tool-call arguments",
                    "kind": "invalid_arguments",
                    "tool": name,
                    "detail": parse_error,
                })
            elif fn is None:
                result = json.dumps({"error": f"Unknown tool: {name}", "kind": "unknown_tool", "tool": name})
            elif cache_key in call_cache:
                # Identical successful call already made this run: reuse it.
                result = call_cache[cache_key]
            else:
                try:
                    result = fn(**args)
                except Exception as exc:
                    # Convert tool exceptions into tool results so the agent can recover.
                    result = json.dumps({"error": str(exc), "kind": "exception", "tool": name})
                if _tool_status(result) == "ok":
                    call_cache[cache_key] = result

            status = _tool_status(result)
            tool_calls.append({
                "tool": name,
                "arguments": args,
                "status": status,
                "result_excerpt": str(result)[:_EXCERPT_CHARS],
                "result": str(result)[:_FULL_RESULT_CHARS],  # used by grounding checks
            })
            _record_host_tool_event({
                "event": "host_tool_execution",
                "tool_call_id": tc.id,
                "tool_name": name,
                "execution_status": "completed" if status == "ok" else "failed",
            })

            # Add the tool result to the conversation so the LLM can continue.
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc.id,
                "name": name,
                "content": result,
            }

            # Preserve the existing conversation transcript behavior.
            messages.append(tool_msg)
            transcript.append(tool_msg)

