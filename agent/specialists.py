from agent.loop import run_agent
from agent.budgets import Budget
from agent.tools import (
    RESEARCH_TOOL_SCHEMAS,
    RESEARCH_TOOL_FUNCTIONS,
    PACKAGE_TOOL_SCHEMAS,
    PACKAGE_TOOL_FUNCTIONS,
)
from agent.mcp_adapter import build_multi_mcp_tool_registry
from pathlib import Path
from agent.mcp_adapter import build_mcp_tool_registry

class ResearchAgent:
    """Specialist agent that researches docs and package APIs through MCP."""

    def __init__(
        self,
        budget: Budget,
        mcp_server_scripts: list[str] | None = None,
    ):
        # Store the agent identity and execution budget.
        self.name = "research"
        self.budget = budget

        # Preserve the original local tools for existing code and tests.
        self.tool_schemas = RESEARCH_TOOL_SCHEMAS
        self.tool_functions = RESEARCH_TOOL_FUNCTIONS

        # When MCP servers are configured, dynamically discover and combine
        # their tools instead of relying on the local tool registry.
        if mcp_server_scripts:
            (
                self.tool_schemas,
                self.tool_functions,
            ) = build_multi_mcp_tool_registry(mcp_server_scripts)

    def run(self, task: str):
        # Pass the discovered schemas and functions into the existing
        # agent loop, which handles LLM tool selection and execution.
        return run_agent(
            question=task,
            budget=self.budget,
            system_prompt=(
        "You are a documentation research specialist. "
        "Research the provided task using available tools. "
        "Only state facts supported by tool results. "
        "Clearly identify missing information."
    ),
            tool_schemas=self.tool_schemas,
            tool_functions=self.tool_functions,
        )
class PackageAgent:
    """Specialist agent for package and version research."""

    def __init__(self, budget: Budget):
        self.name = "package"
        self.budget = budget

    def run(self, task: str):
        return run_agent(
            question=(
                "You are a package specialist. "
                "Focus on package names, versions, compatibility, "
                "and installation details.\n\n"
                f"Task: {task}"
            ),
            budget=self.budget,
            tool_schemas=PACKAGE_TOOL_SCHEMAS,
            tool_functions=PACKAGE_TOOL_FUNCTIONS,
        )