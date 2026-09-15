import json
import time
from dataclasses import dataclass, field

from agent.budgets import Budget, BudgetExceeded, BudgetTracker
from agent.config import AGENT_MODEL, price_for
from agent.tools import TOOL_SCHEMAS, call_tool

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


def _budget_result(tracker: BudgetTracker, reason: str, transcript: list[dict]) -> RunResult:
    return RunResult(
        answer=None,
        terminated_by_budget=True,
        budget_reason=reason,
        iterations=tracker.iterations,
        total_tokens=tracker.total_tokens,
        total_cost_usd=tracker.total_cost_usd,
        wall_seconds=tracker.elapsed(),
        transcript=transcript,
    )


def run_agent(question: str, budget: Budget, client=None) -> RunResult:
    if client is None:
        from groq import Groq

        client = Groq()

    tracker = BudgetTracker(budget=budget)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    transcript = [dict(m) for m in messages]

    while True:
        try:
            tracker.start_iteration()
        except BudgetExceeded as exc:
            return _budget_result(tracker, exc.reason, transcript)

        response = client.chat.completions.create(
            model=AGENT_MODEL, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto"
        )
        usage = response.usage
        price_in, price_out = price_for(AGENT_MODEL)
        try:
            tracker.record_usage(usage.prompt_tokens, usage.completion_tokens, price_in, price_out)
        except BudgetExceeded as exc:
            return _budget_result(tracker, exc.reason, transcript)

        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)

        if not tool_calls:
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
            )

        assistant_msg = {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        }
        messages.append(assistant_msg)
        transcript.append(assistant_msg)

        for tc in tool_calls:
            args = json.loads(tc.function.arguments)
            result = call_tool(tc.function.name, args)
            tool_msg = {"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": result}
            messages.append(tool_msg)
            transcript.append(tool_msg)
