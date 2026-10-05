"""One-off script: run the same failing question through the research agent
over the real docs_server MCP server, live, and dump the transcript to JSON
so error_before_after.md can quote it. Run once with the old docs_server.py
(label=before) and once with the rewritten one (label=after). tool_choice is
forced on the first turn only so the model can't skip straight to a guess --
we want to see how it handles the tool's actual response either way. Loops
up to 3 turns so a model that keeps retrying the search gets the chance to,
instead of being cut off after exactly one tool call."""
import json
import sys

from dotenv import load_dotenv

load_dotenv()

from groq import Groq

from agent.config import AGENT_MODEL
from agent.mcp_adapter import build_mcp_tool_registry

label = sys.argv[1]
QUESTION = (
    "What are the body parameters for create_issue in API version 2026-01-01, "
    "and is anything deprecated at that version?"
)
SYSTEM_PROMPT = (
    "You help developers migrate code between GitHub API versions. Only "
    "state facts a tool call returned to you -- never guess a parameter "
    "name, default, or deprecation status."
)

tool_schemas, tool_functions = build_mcp_tool_registry(
    "agent/mcp_servers/docs_server.py"
)

client = Groq()
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": QUESTION},
]

final_content = None
for turn in range(3):
    tool_choice = "required" if turn == 0 else "auto"
    response = client.chat.completions.create(
        model=AGENT_MODEL, messages=messages, tools=tool_schemas, tool_choice=tool_choice
    )
    msg = response.choices[0].message

    if not msg.tool_calls:
        messages.append({"role": "assistant", "content": msg.content})
        final_content = msg.content
        break

    messages.append({
        "role": "assistant",
        "content": msg.content,
        "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ],
    })
    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)
        result = tool_functions[tc.function.name](**args)
        messages.append({
            "role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": result,
        })

json.dump(
    {"question": QUESTION, "answer": final_content, "transcript": messages},
    open(f"transcript_{label}.json", "w"),
    indent=2,
)
print(f"--- {label} ---")
print(final_content)
