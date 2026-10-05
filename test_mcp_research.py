# Import Path so we can construct the MCP server's location reliably.
from pathlib import Path

# Import json to read the MCP server list from the external config file.
import json

# Import Budget to limit the agent's token usage and execution cost.
from agent.budgets import Budget

# Import ResearchAgent to run documentation research through MCP.
from agent.specialists import ResearchAgent
# Import os so this test can enable optional host-level tool capture.
import os

# Resolve the project root so the server path works from any directory.
PROJECT_ROOT = Path(__file__).resolve().parent

# The set of MCP servers the agent connects to lives entirely in
# mcp_config.json. Adding/removing a server is a config edit here -- it
# never requires touching agent/specialists.py or agent/mcp_adapter.py,
# which discover tools dynamically from whatever servers are listed.
with open(PROJECT_ROOT / "mcp_config.json", encoding="utf-8") as config_file:
    MCP_SERVERS = [
        str(PROJECT_ROOT / server_path)
        for server_path in json.load(config_file)["mcp_servers"]
    ]

# Create a research agent that discovers tools from both MCP servers.

# Create a budget to constrain the agent's model and tool execution.
# Set limits for the agent to control iterations, token usage, cost, and runtime.
budget = Budget(
    max_iterations=5,       # Allow at most 5 LLM/tool loop iterations.
    max_tokens=4000,        # Limit total token usage for this run.
    max_cost_usd=0.10,      # Cap the estimated model cost at $0.10.
    max_wall_seconds=60,    # Stop the run after 60 seconds.
)

# Initialize ResearchAgent with the MCP server so it discovers MCP tools.
research_agent = ResearchAgent(
    budget=budget,
    mcp_server_scripts=MCP_SERVERS,
)

# Enable host-level tool decision capture for this test run.
os.environ["HOST_TOOL_CAPTURE"] = str(
    PROJECT_ROOT / "host_tool_calls.json"
)

## Ask a question that should require package API and deprecation tools.
result = research_agent.run(
    "For the create_issue endpoint, explain its API parameters "
    "and whether any fields are deprecated in API version 2025-06-01."
)

# Print the result to inspect which tools the agent used.
print(result)