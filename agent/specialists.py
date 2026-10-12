import json
from pathlib import Path

from agent.budgets import Budget
from agent.loop import run_agent
from agent.mcp_adapter import McpRegistry

REPO_ROOT = Path(__file__).resolve().parent.parent


class Specialist:
    """A specialist agent whose tools come from an McpRegistry over its
    configured MCP servers. The server list is static config; the tools are
    discovered at construction and re-discovered by every run() when the
    registry is empty, stale, or a server was unavailable -- so a tool newly
    exposed by a configured server is picked up without code changes or a
    restart.
    """

    def __init__(
        self,
        name: str,
        description: str,
        mcp_servers: list,
        budget: Budget,
        approved_servers=(),
        ttl_seconds: float = 300.0,
        consent_callback=None,
    ):
        self.name = name
        self.description = description
        self.budget = budget
        # Policy violations (bad path, etc.) raise here; an unreachable
        # server does not -- it is recorded as UNAVAILABLE and retried per run.
        self.registry = McpRegistry(
            mcp_servers, approved_servers=approved_servers, ttl_seconds=ttl_seconds,
            consent_callback=consent_callback,
        )
        self.registry.ensure_fresh()

    @property
    def tool_names(self) -> list[str]:
        return self.registry.tool_names()

    @property
    def tool_schemas(self) -> list:
        return self.registry.tool_schemas()

    @property
    def tool_functions(self) -> dict:
        return self.registry.tool_functions()

    def _system_prompt(self, tool_names: list[str]) -> str:
        prompt = (
            f"{self.description}\n\n"
            f"The only tools available to you are: {', '.join(tool_names)}. "
            "Use only these -- never invent a tool name. Base every claim on "
            "a successful tool result; if a tool returns an error, say so "
            "instead of answering from memory."
        )
        problems = self.registry.problems()
        if problems:
            prompt += f" Some tool sources are currently unavailable: {problems}."
        return prompt

    def run(self, task: str, client=None):
        self.registry.ensure_fresh()
        self.registry.raise_if_unusable()
        tool_functions = self.registry.tool_functions()
        return run_agent(
            question=task,
            budget=self.budget,
            client=client,
            system_prompt=self._system_prompt(sorted(tool_functions)),
            tool_schemas=self.registry.tool_schemas(),
            tool_functions=tool_functions,
        )

    def close(self) -> None:
        self.registry.close()


def load_specialists(
    config_path: Path, budget: Budget, approved_servers=(), consent_callback=None
) -> list[Specialist]:
    """Build one Specialist per entry in a specialists.json-shaped config.

    Each "mcp_servers" item is either a path string or an object
    {"path", "requires_consent", "permitted_tools", "env_passthrough"}.
    Paths resolve against the repo root and must stay inside it.
    """

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))

    return [
        Specialist(
            name=entry["name"],
            description=entry["description"],
            mcp_servers=entry["mcp_servers"],
            budget=budget,
            approved_servers=approved_servers,
            consent_callback=consent_callback,
        )
        for entry in config["specialists"]
    ]


def close_specialists(specialists) -> None:
    for specialist in specialists:
        close = getattr(specialist, "close", None)
        if close:
            close()
