import json

import pytest
from unittest.mock import patch

from agent.budgets import Budget
from agent.specialists import Specialist, load_specialists


def _budget():
    return Budget(max_iterations=3, max_tokens=1000, max_cost_usd=0.01, max_wall_seconds=30)


def test_specialist_builds_tools_and_grounded_system_prompt():
    fake_schemas = [{"type": "function", "function": {"name": "search_documentation", "parameters": {}}}]
    fake_functions = {"search_documentation": lambda **kwargs: "ok"}

    with patch(
        "agent.specialists.build_multi_mcp_tool_registry",
        return_value=(fake_schemas, fake_functions),
    ) as mock_build:
        specialist = Specialist(
            name="code_sample_worker",
            description="Prose documentation search specialist.",
            mcp_servers=["agent/mcp_servers/docs_server.py"],
            budget=_budget(),
        )

    mock_build.assert_called_once_with(["agent/mcp_servers/docs_server.py"])
    assert specialist.name == "code_sample_worker"
    assert specialist.tool_schemas == fake_schemas
    assert specialist.tool_functions == fake_functions
    assert "Prose documentation search specialist." in specialist.system_prompt
    assert "search_documentation" in specialist.system_prompt


def test_specialist_run_delegates_to_run_agent_with_its_own_tools():
    fake_schemas = [{"type": "function", "function": {"name": "search_documentation", "parameters": {}}}]
    fake_functions = {"search_documentation": lambda **kwargs: "ok"}

    with patch(
        "agent.specialists.build_multi_mcp_tool_registry",
        return_value=(fake_schemas, fake_functions),
    ):
        specialist = Specialist(
            name="code_sample_worker",
            description="Prose documentation search specialist.",
            mcp_servers=["agent/mcp_servers/docs_server.py"],
            budget=_budget(),
        )

    with patch("agent.specialists.run_agent") as mock_run_agent:
        mock_run_agent.return_value = "sentinel-result"
        result = specialist.run("What are the body params for create_issue?", client="fake-client")

    assert result == "sentinel-result"
    mock_run_agent.assert_called_once_with(
        question="What are the body params for create_issue?",
        budget=specialist.budget,
        client="fake-client",
        system_prompt=specialist.system_prompt,
        tool_schemas=fake_schemas,
        tool_functions=fake_functions,
    )


def test_load_specialists_builds_one_specialist_per_config_entry(tmp_path):
    config_path = tmp_path / "specialists.json"
    config_path.write_text(json.dumps({
        "specialists": [
            {
                "name": "deprecation_worker",
                "description": "Deprecation specialist.",
                "mcp_servers": ["agent/mcp_servers/package_server.py"],
            },
            {
                "name": "code_sample_worker",
                "description": "Code sample specialist.",
                "mcp_servers": ["agent/mcp_servers/docs_server.py"],
            },
        ]
    }))

    with patch(
        "agent.specialists.build_multi_mcp_tool_registry",
        return_value=([], {}),
    ) as mock_build:
        specialists = load_specialists(config_path, budget=_budget())

    assert [s.name for s in specialists] == ["deprecation_worker", "code_sample_worker"]
    assert mock_build.call_count == 2


def test_load_specialists_propagates_mcp_discovery_errors(tmp_path):
    config_path = tmp_path / "specialists.json"
    config_path.write_text(json.dumps({
        "specialists": [
            {
                "name": "broken_worker",
                "description": "A specialist whose server fails to start.",
                "mcp_servers": ["agent/mcp_servers/does_not_exist.py"],
            },
        ]
    }))

    with patch(
        "agent.specialists.build_multi_mcp_tool_registry",
        side_effect=RuntimeError("server process exited"),
    ):
        with pytest.raises(RuntimeError, match="server process exited"):
            load_specialists(config_path, budget=_budget())
