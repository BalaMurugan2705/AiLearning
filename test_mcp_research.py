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

# Release the persistent MCP server connections.
research_specialist.close()
