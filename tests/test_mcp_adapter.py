"""Tests for the MCP registry against a real stdio MCP server
(tests/fixtures/mcp_probe_server.py)."""

import json
from pathlib import Path

import pytest

from agent.errors import McpConsentRequired, McpPolicyError, McpServerUnavailable
from agent.mcp_adapter import (
    AVAILABLE, CONSENT_REQUIRED, NOT_DISCOVERED, UNAVAILABLE, McpRegistry, parse_server_entry,
)

PROBE = "tests/fixtures/mcp_probe_server.py"


@pytest.fixture
def registry():
    created = []

    def make(*servers, **kw):
        reg = McpRegistry(list(servers) or [PROBE], **kw)
        created.append(reg)
        return reg

    yield make
    for reg in created:
        reg.close()


def test_discovers_tools_resources_and_prompts(registry):
    reg = registry()
    assert reg.status(PROBE) == NOT_DISCOVERED
    reg.ensure_fresh()
    assert reg.status(PROBE) == AVAILABLE
    names = reg.tool_names()
    assert {"echo", "boom"} <= set(names)
    schema_names = {s["function"]["name"] for s in reg.tool_schemas()}
    assert {"read_mcp_resource", "get_mcp_prompt"} <= schema_names
    assert json.loads(reg.read_resource("probe://note"))["content"] == ["resource-body"]
    assert "hello bob" in reg.get_prompt("greet", {"name": "bob"})


def test_connection_is_reused_across_calls(registry):
    reg = registry()
    reg.ensure_fresh()
    first = reg._conns[reg.configs[0].id]
    for _ in range(3):
        assert json.loads(reg.call_tool("echo", {"text": "x"}))["content"] == ["x"]
    reg.ensure_fresh()
    assert reg._conns[reg.configs[0].id] is first


def test_host_validates_arguments_before_calling_server(registry):
    reg = registry()
    reg.ensure_fresh()
    for bad in ({}, {"text": 5}, {"text": "a", "bogus": 1}):
        out = json.loads(reg.call_tool("echo", bad))
        assert out["kind"] == "invalid_arguments" and out["detail"]


def test_server_error_detail_and_auth_kind_are_preserved(registry):
    reg = registry()
    reg.ensure_fresh()
    out = json.loads(reg.call_tool("boom", {"x": "a"}))
    assert out["kind"] == "auth"
    assert "401" in out["detail"]


def test_new_tool_is_picked_up_after_ttl_without_code_changes(registry, tmp_path):
    flag = tmp_path / "flag"
    now = [0.0]
    entry = {"path": PROBE, "env_passthrough": ["MCP_PROBE_EXTRA_FLAG"]}
    import os
    os.environ["MCP_PROBE_EXTRA_FLAG"] = str(flag)
    try:
        reg = registry(entry, ttl_seconds=10, clock=lambda: now[0])
        reg.ensure_fresh()
        assert "brand_new_tool" not in reg.tool_names()
        # The running server won't change; force a reconnect by closing it,
        # as would happen after a server upgrade/restart.
        flag.write_text("x")
        reg._conns[reg.configs[0].id].close()
        now[0] = 11  # past ttl -> stale
        reg.ensure_fresh()
        assert "brand_new_tool" in reg.tool_names()
        assert json.loads(reg.call_tool("brand_new_tool", {"x": 5}))["content"] == ["new:5"]
    finally:
        del os.environ["MCP_PROBE_EXTRA_FLAG"]


def test_subprocess_environment_does_not_leak_secrets(registry, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN_FOR_TEST", "s3cret")
    reg = registry()
    reg.ensure_fresh()
    assert json.loads(reg.call_tool("leaked_secret", {}))["content"] == ["absent"]


def test_permitted_tools_allowlist_hides_other_tools(registry):
    reg = registry({"path": PROBE, "permitted_tools": ["echo"]})
    reg.ensure_fresh()
    assert reg.tool_names() == ["echo"]
    assert json.loads(reg.call_tool("boom", {"x": "a"}))["kind"] == "unknown_tool"


def test_consent_required_server_is_not_connected_until_approved(registry):
    reg = registry({"path": PROBE, "requires_consent": True})
    reg.ensure_fresh()
    assert reg.status(PROBE) == CONSENT_REQUIRED
    assert not reg._conns  # never launched
    with pytest.raises(McpConsentRequired):
        reg.raise_if_unusable()
    reg.approve(parse_server_entry(PROBE).path)
    reg.ensure_fresh()
    assert reg.status(PROBE) == AVAILABLE


def test_path_policy_blocks_escape_and_missing_scripts():
    with pytest.raises(McpPolicyError):
        parse_server_entry("../outside.py")
    with pytest.raises(McpPolicyError):
        parse_server_entry("/bin/sh")
    with pytest.raises(McpPolicyError):
        parse_server_entry("agent/mcp_servers/missing.py")


def test_unavailable_server_is_distinct_from_undiscovered_and_recovers(registry, tmp_path):
    script = tmp_path / "flaky.py"
    script.write_text("raise SystemExit(1)\n")
    reg = registry(str(script), allowed_roots=(tmp_path,))
    assert reg.status(script) == NOT_DISCOVERED
    reg.ensure_fresh()
    assert reg.status(script) == UNAVAILABLE
    with pytest.raises(McpServerUnavailable):
        reg.raise_if_unusable()
    script.write_text(Path(PROBE).read_text())  # server comes back
    reg.ensure_fresh()
    assert reg.status(script) == AVAILABLE


def test_partial_outage_keeps_working_servers_usable(registry, tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("raise SystemExit(1)\n")
    reg = registry(PROBE, str(bad), allowed_roots=(tmp_path, Path.cwd()))
    reg.ensure_fresh()
    assert "echo" in reg.tool_names()
    assert "bad.py" in reg.problems()


def test_dead_connection_is_reported_then_reconnected(registry):
    reg = registry()
    reg.ensure_fresh()
    conn = reg._conns[reg.configs[0].id]
    conn.close()
    out = json.loads(reg.call_tool("echo", {"text": "again"}))
    assert out["content"] == ["again"]  # call_tool reconnects


def test_consent_callback_grants_access_and_is_asked_once(registry):
    asked = []

    def allow(cfg):
        asked.append(cfg.path.name)
        return True

    reg = registry({"path": PROBE, "requires_consent": True}, consent_callback=allow)
    reg.ensure_fresh()
    reg.ensure_fresh()
    assert reg.status(PROBE) == AVAILABLE
    assert asked == ["mcp_probe_server.py"]


def test_consent_callback_denial_blocks_and_does_not_nag(registry):
    asked = []

    def deny(cfg):
        asked.append(1)
        return False

    reg = registry({"path": PROBE, "requires_consent": True}, consent_callback=deny)
    reg.ensure_fresh()
    reg.ensure_fresh()
    assert reg.status(PROBE) == CONSENT_REQUIRED
    assert not reg._conns and len(asked) == 1
    reg.approve(PROBE)  # explicit approval overrides an earlier denial
    reg.ensure_fresh()
    assert reg.status(PROBE) == AVAILABLE


def test_status_and_approve_resolve_relative_paths_against_repo_root(registry, monkeypatch, tmp_path):
    reg = registry({"path": PROBE, "requires_consent": True})
    monkeypatch.chdir(tmp_path)  # a different cwd must not change resolution
    reg.approve(PROBE)
    reg.ensure_fresh()
    assert reg.status(PROBE) == AVAILABLE


def _kill_server_children():
    import os, signal, subprocess
    kids = [int(x) for x in subprocess.run(
        ["pgrep", "-P", str(os.getpid())], capture_output=True, text=True).stdout.split()]
    for pid in kids:
        os.kill(pid, signal.SIGKILL)
    assert kids, "expected a running server child process"


def test_killed_server_process_is_detected_and_call_reconnects(registry):
    import time
    reg = registry()
    reg.ensure_fresh()
    first = reg._conns[reg.configs[0].id]
    _kill_server_children()
    time.sleep(0.5)
    out = json.loads(reg.call_tool("echo", {"text": "back"}))
    assert out["content"] == ["back"]  # transparently reconnected, call retried once
    assert reg._conns[reg.configs[0].id] is not first
    assert reg.status(PROBE) == AVAILABLE


def test_ensure_fresh_repairs_a_dead_connection_after_failed_call(registry):
    import time
    reg = registry()
    reg.ensure_fresh()
    _kill_server_children()
    time.sleep(0.5)
    out = json.loads(reg.call_tool("echo", {"text": "x"}))
    assert out["content"] == ["x"]
    reg.ensure_fresh()
    assert json.loads(reg.call_tool("echo", {"text": "y"}))["content"] == ["y"]
