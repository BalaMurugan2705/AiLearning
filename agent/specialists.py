import json
from pathlib import Path

from agent.budgets import Budget
from agent.loop import run_agent
from agent.mcp_adapter import build_multi_mcp_tool_registry

REPO_ROOT = Path(__file__).resolve().parent.parent


class Specialist:
    """A specialist agent whose tools are discovered dynamically from one
    or more MCP servers, instead of calling local Python functions
    directly. Construction (and MCP discovery) happens once; .run() can
    be called for any number of questions afterward.
    """

    def __init__(self, name: str, description: str, mcp_servers: list[str], budget: Budget):
        self.name = name
        self.description = description
        self.budget = budget

        self.tool_schemas, self.tool_functions = build_multi_mcp_tool_registry(mcp_servers)

        self.system_prompt = (
            f"{description}\n\n"
            f"The only tools available to you are: {', '.join(sorted(self.tool_functions))}. "
            "Use only these -- never invent a tool name."
        )

    def run(self, task: str, client=None):
        return run_agent(
            question=task,
            budget=self.budget,
            client=client,
            system_prompt=self.system_prompt,
            tool_schemas=self.tool_schemas,
            tool_functions=self.tool_functions,
        )


def load_specialists(config_path: Path, budget: Budget) -> list[Specialist]:
    """Build one Specialist per entry in a specialists.json-shaped config
    file. MCP server paths in the config are resolved relative to the
    repo root, same convention test_mcp_research.py already used for
    mcp_config.json.
    """

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))

    specialists = []
    for entry in config["specialists"]:
        mcp_servers = [
            str(REPO_ROOT / server_path) for server_path in entry["mcp_servers"]
        ]
        specialists.append(
            Specialist(
                name=entry["name"],
                description=entry["description"],
                mcp_servers=mcp_servers,
                budget=budget,
            )
        )
    return specialists
