from agent.config import AGENT_MODEL, price_for
from agent.loop import RunResult
from agent.spec import API_VERSIONS, ENDPOINT_NAMES
from agent.tools import call_tool
from agent.budgets import BudgetTracker, Budget

# Deliberately does not mention tools at all: the workflow has already run
# all 3 tools itself by the time this prompt is used, so this call is pure
# synthesis. Reusing agent.loop.SYSTEM_PROMPT here (which says "you have
# tools") made the model keep attempting tool calls even with tools=None
# and even with tool_choice="none" explicitly set -- a real quirk of this
# model on Groq, not something the API parameters could talk it out of.
SYNTHESIS_PROMPT = (
    "You write precise technical answers using only the context you are "
    "given below -- search results, an OpenAPI parameter list, and a "
    "deprecation check. Never guess or add information not present in that "
    "context. If the context does not answer the question, say so plainly. "
    "Respond in plain text only."
)

_ENDPOINT_KEYWORDS = {
    "create_issue": ["issue"],
    "create_pull_request": ["pull request"],
    "create_repository": ["repository", "repo "],
    "create_release": ["release"],
    "render_markdown": ["markdown"],
}


def extract_endpoint(question: str) -> str | None:
    lowered = question.lower()
    for endpoint, keywords in _ENDPOINT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return endpoint
    return None


def extract_api_version(question: str) -> str:
    for version in API_VERSIONS:
        if version in question:
            return version
    return API_VERSIONS[-1]


def run_workflow(question: str, client=None) -> RunResult:
    if client is None:
        from groq import Groq

        client = Groq()

    # An unlimited tracker: the workflow has no loop to run away, but reusing
    # BudgetTracker keeps token/cost accounting identical to the agent's.
    tracker = BudgetTracker(
        budget=Budget(max_iterations=1, max_tokens=10**9, max_cost_usd=10**9, max_wall_seconds=10**9)
    )
    tracker.start_iteration()

    endpoint = extract_endpoint(question) or ENDPOINT_NAMES[0]
    api_version = extract_api_version(question)

    transcript: list[dict] = []
    docs_result = call_tool("search_docs", {"query": question})
    transcript.append({"role": "tool", "name": "search_docs", "content": docs_result})

    spec_result = call_tool("get_openapi_spec", {"endpoint": endpoint, "api_version": api_version})
    transcript.append({"role": "tool", "name": "get_openapi_spec", "content": spec_result})

    deprecation_result = call_tool("check_deprecation", {"endpoint": endpoint, "api_version": api_version})
    transcript.append({"role": "tool", "name": "check_deprecation", "content": deprecation_result})

    context = (
        f"Docs search results: {docs_result}\n\n"
        f"OpenAPI spec: {spec_result}\n\n"
        f"Deprecation check: {deprecation_result}"
    )
    messages = [
        {"role": "system", "content": SYNTHESIS_PROMPT},
        {"role": "user", "content": f"{context}\n\nQuestion: {question}"},
    ]
    transcript.extend(dict(m) for m in messages)

    response = client.chat.completions.create(model=AGENT_MODEL, messages=messages)
    usage = response.usage
    price_in, price_out = price_for(AGENT_MODEL)
    tracker.record_usage(usage.prompt_tokens, usage.completion_tokens, price_in, price_out)

    answer = response.choices[0].message.content
    transcript.append({"role": "assistant", "content": answer})

    return RunResult(
        answer=answer,
        terminated_by_budget=False,
        budget_reason=None,
        iterations=1,
        total_tokens=tracker.total_tokens,
        total_cost_usd=tracker.total_cost_usd,
        wall_seconds=tracker.elapsed(),
        transcript=transcript,
    )
