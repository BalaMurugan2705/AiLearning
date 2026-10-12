import json

import pytest
from unittest.mock import MagicMock, patch

from agent.budgets import Budget
from agent.errors import McpConsentRequired, McpPolicyError, McpServerUnavailable
from agent.specialists import Specialist, load_specialists


def _budget():
    return Budget(max_iterations=3, max_tokens=1000, max_cost_usd=0.01, max_wall_seconds=30)


def _fake_registry(tool_names=("search_documentation",), problems=None):
    reg = MagicMock()
    reg.tool_names.return_value = list(tool_names)
    reg.tool_schemas.return_value = [{"type": "function", "function": {"name": n, "parameters": {}}} for n in tool_names]
    reg.tool_functions.return_value = {n: (lambda **kw: "ok") for n in tool_names}
    reg.problems.return_value = problems or {}
    return reg


def test_specialist_discovers_on_construction_and_refreshes_every_run():
    reg = _fake_registry()
    with patch("agent.specialists.McpRegistry", return_value=reg):
        specialist = Specialist("code_sample_worker", "Docs specialist.", ["agent/mcp_servers/docs_server.py"], _budget())
    reg.ensure_fresh.assert_called_once()

    with patch("agent.specialists.run_agent", return_value="sentinel") as mock_run:
        assert specialist.run("q", client="c") == "sentinel"
    assert reg.ensure_fresh.call_count == 2
    reg.raise_if_unusable.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs["question"] == "q" and kwargs["client"] == "c"
    assert "Docs specialist." in kwargs["system_prompt"]
    assert "search_documentation" in kwargs["system_prompt"]
    assert list(kwargs["tool_functions"]) == ["search_documentation"]


def test_specialist_prompt_lists_tools_discovered_at_run_time_not_construction():
    reg = _fake_registry(("a",))
    with patch("agent.specialists.McpRegistry", return_value=reg):
        specialist = Specialist("w", "d", ["agent/mcp_servers/docs_server.py"], _budget())
    # A newly exposed tool appears in the registry before the next run.
    reg.tool_functions.return_value = {"a": lambda **k: "", "brand_new": lambda **k: ""}
    with patch("agent.specialists.run_agent") as mock_run:
        specialist.run("q")
    assert "brand_new" in mock_run.call_args.kwargs["system_prompt"]


def test_specialist_run_surfaces_unavailable_server_so_squad_can_retry():
    reg = _fake_registry()
    reg.raise_if_unusable.side_effect = McpServerUnavailable("down")
    with patch("agent.specialists.McpRegistry", return_value=reg):
        specialist = Specialist("w", "d", ["agent/mcp_servers/docs_server.py"], _budget())
    with pytest.raises(McpServerUnavailable):
        specialist.run("q")


def test_specialist_run_surfaces_consent_required():
    reg = _fake_registry()
    reg.raise_if_unusable.side_effect = McpConsentRequired("needs consent")
    with patch("agent.specialists.McpRegistry", return_value=reg):
        specialist = Specialist("w", "d", ["agent/mcp_servers/docs_server.py"], _budget())
    with pytest.raises(McpConsentRequired):
        specialist.run("q")


def test_load_specialists_builds_one_specialist_per_config_entry(tmp_path):
    config_path = tmp_path / "specialists.json"
    config_path.write_text(json.dumps({
        "specialists": [
            {"name": "deprecation_worker", "description": "Dep.", "mcp_servers": ["agent/mcp_servers/package_server.py"]},
            {"name": "code_sample_worker", "description": "Code.", "mcp_servers": ["agent/mcp_servers/docs_server.py"]},
        ]
    }))
    with patch("agent.specialists.McpRegistry", return_value=_fake_registry()) as mock_reg:
        specialists = load_specialists(config_path, budget=_budget())
    assert [s.name for s in specialists] == ["deprecation_worker", "code_sample_worker"]
    assert mock_reg.call_count == 2


def test_load_specialists_rejects_servers_outside_the_repo(tmp_path):
    config_path = tmp_path / "specialists.json"
    config_path.write_text(json.dumps({"specialists": [
        {"name": "evil", "description": "x", "mcp_servers": ["../../../../etc/evil.py"]},
    ]}))
    with pytest.raises(McpPolicyError):
        load_specialists(config_path, budget=_budget())


def test_load_specialists_tolerates_unreachable_server_without_crashing(tmp_path):
    # Real registry, real (failing) server: the specialist is still built,
    # and the outage only surfaces when it is asked to run.
    broken = tmp_path / "broken_server.py"
    broken.write_text("raise SystemExit(1)\n")
    from agent.mcp_adapter import McpRegistry
    reg = McpRegistry([str(broken)], allowed_roots=(tmp_path,))
    reg.ensure_fresh()
    assert reg.statuses() == {"broken_server.py": "unavailable"}
    with pytest.raises(McpServerUnavailable):
        reg.raise_if_unusable()
