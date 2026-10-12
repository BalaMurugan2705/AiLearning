"""MCP client layer.

Server *configuration* is static (config file); the *capabilities* of each
server (tools, resources, prompts) are discovered dynamically and cached in
an McpRegistry that refreshes when empty, stale, or after a failure.

Connections are persistent (one stdio session per server, run on a private
event-loop thread) and are reused until close(). Launching a server is
gated by a policy (path allowlist, minimal environment, optional per-server
consent and tool allowlist).
"""

import asyncio
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from agent.errors import McpConsentRequired, McpPolicyError, McpServerUnavailable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Only these variables reach a server subprocess. Secrets such as API keys
# are NOT forwarded unless a server entry lists them in "env_passthrough".
_ENV_ALLOWLIST = (
    "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "VIRTUAL_ENV", "SYSTEMROOT",
    "HF_HOME", "TRANSFORMERS_CACHE", "TOKENIZERS_PARALLELISM",
)  # PYTHONPATH is handled separately: repo root first, then the parent's.

NOT_DISCOVERED = "not_discovered"
AVAILABLE = "available"
UNAVAILABLE = "unavailable"
CONSENT_REQUIRED = "consent_required"

READ_RESOURCE_TOOL = "read_mcp_resource"
GET_PROMPT_TOOL = "get_mcp_prompt"

_AUTH_PATTERN = re.compile(
    r"\b(401|403|unauthori[sz]ed|forbidden|permission|credential|token expired|access denied)\b",
    re.IGNORECASE,
)


def _record_mcp_wire_event(direction: str, annotation: str, message: dict) -> None:
    """Append an MCP event to the file named by MCP_WIRE_CAPTURE (opt-in)."""
    capture_path = os.environ.get("MCP_WIRE_CAPTURE")
    if not capture_path:
        return
    try:
        with open(capture_path, "r", encoding="utf-8") as file:
            events = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        events = []
    events.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "annotation": annotation,
        "message": message,
    })
    with open(capture_path, "w", encoding="utf-8") as file:
        json.dump(events, file, indent=2)


# --------------------------------------------------------------------------
# Server configuration and launch policy
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ServerConfig:
    path: Path
    requires_consent: bool = False
    permitted_tools: frozenset | None = None
    env_passthrough: tuple = ()

    @property
    def id(self) -> str:
        return str(self.path)


def parse_server_entry(entry, allowed_roots=(REPO_ROOT,)) -> ServerConfig:
    """Accept either a bare path string or a dict with policy fields, and
    enforce the launch policy: the script must be an existing .py file
    inside an allowed root (blocks '..' and absolute-path escapes)."""

    if isinstance(entry, ServerConfig):
        return entry
    if isinstance(entry, (str, Path)):
        entry = {"path": str(entry)}
    raw = Path(entry["path"])
    path = (raw if raw.is_absolute() else REPO_ROOT / raw).resolve()

    roots = [Path(r).resolve() for r in allowed_roots]
    if not any(path.is_relative_to(root) for root in roots):
        raise McpPolicyError(f"MCP server path {path} is outside the allowed roots")
    if path.suffix != ".py" or not path.is_file():
        raise McpPolicyError(f"MCP server script not found or not a .py file: {path}")

    permitted = entry.get("permitted_tools")
    return ServerConfig(
        path=path,
        requires_consent=bool(entry.get("requires_consent", False)),
        permitted_tools=frozenset(permitted) if permitted is not None else None,
        env_passthrough=tuple(entry.get("env_passthrough", ())),
    )


def _cfg_id(server) -> str:
    """Canonical id for a server path; relative paths resolve against the repo root."""
    if isinstance(server, ServerConfig):
        return server.id
    raw = Path(server)
    return str((raw if raw.is_absolute() else REPO_ROOT / raw).resolve())


def interactive_consent(cfg: "ServerConfig") -> bool:
    """Ready-made consent_callback: ask on the terminal (denies when there is no TTY)."""
    if not sys.stdin.isatty():
        return False
    return input(f"Allow connecting to MCP server {cfg.path.name}? [y/N] ").strip().lower() in ("y", "yes")


def _server_env(cfg: ServerConfig) -> dict:
    env = {k: os.environ[k] for k in (*_ENV_ALLOWLIST, *cfg.env_passthrough) if k in os.environ}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT), os.environ.get("PYTHONPATH")]))
    return env


# --------------------------------------------------------------------------
# Persistent connection
# --------------------------------------------------------------------------

class _Connection:
    """One long-lived MCP stdio session, owned by a private event-loop thread
    so synchronous agent code can reuse it across calls."""

    def __init__(self, cfg: ServerConfig, call_timeout: float = 60.0, start_timeout: float = 60.0):
        self.cfg = cfg
        self.call_timeout = call_timeout
        self.start_timeout = start_timeout
        self.capabilities = None
        self._session = None
        self._error = None
        self._ready = threading.Event()
        self._dead = False
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._stop = None

    async def _serve(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=sys.executable,
            args=[str(self.cfg.path)],
            env=_server_env(self.cfg),
            cwd=str(REPO_ROOT),
        )
        try:
            self._stop = asyncio.Event()
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    init = await session.initialize()
                    self.capabilities = init.capabilities
                    self._session = session
                    _record_mcp_wire_event(
                        "client_to_server", "MCP session initialized",
                        {"method": "initialize", "server": self.cfg.id},
                    )
                    self._ready.set()
                    await self._stop.wait()
        except BaseException as exc:  # noqa: BLE001 - surfaced via start()/alive
            self._error = exc
        finally:
            self._dead = True
            self._ready.set()

    def start(self):
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        if not self._ready.wait(self.start_timeout) or self._error or not self._session:
            self.close()
            raise McpServerUnavailable(
                f"MCP server {self.cfg.path.name} failed to start: {_describe(self._error) or 'timeout'}"
            )
        return self

    @property
    def alive(self) -> bool:
        return not self._dead and self._session is not None

    def request(self, make_coro):
        if not self.alive:
            raise McpServerUnavailable(f"MCP server {self.cfg.path.name} is not connected")
        future = asyncio.run_coroutine_threadsafe(make_coro(self._session), self._loop)
        try:
            return future.result(self.call_timeout)
        except Exception as exc:
            future.cancel()
            if _is_dead_connection_error(exc):
                self._dead = True  # the SDK session does not end by itself when the child dies
            if not self.alive:
                raise McpServerUnavailable(
                    f"MCP server {self.cfg.path.name} connection lost: {_describe(exc)}"
                ) from exc
            raise

    def close(self):
        if self._loop.is_running():
            if self._stop is not None:
                self._loop.call_soon_threadsafe(self._stop.set)
            time.sleep(0.05)
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
        self._dead = True


_DEAD_CONNECTION_ERRORS = {
    "ClosedResourceError", "BrokenResourceError", "EndOfStream",
    "BrokenPipeError", "ConnectionResetError", "ConnectionAbortedError",
}


def _is_dead_connection_error(exc) -> bool:
    """True when the failure means the server process/stream is gone (as opposed
    to the tool itself failing), so reconnecting is the right response."""
    if exc is None:
        return False
    if type(exc).__name__ in _DEAD_CONNECTION_ERRORS:
        return True
    if type(exc).__name__ == "McpError" and "connection closed" in str(exc).lower():
        return True
    subs = getattr(exc, "exceptions", None) or ()
    return any(_is_dead_connection_error(e) for e in subs) or _is_dead_connection_error(exc.__cause__)


def _describe(exc) -> str:
    if exc is None:
        return ""
    subs = getattr(exc, "exceptions", None)
    if subs:
        return "; ".join(_describe(s) for s in subs)
    return f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------
# Capability registry
# --------------------------------------------------------------------------

@dataclass
class _Entry:
    status: str = NOT_DISCOVERED
    tools: list = field(default_factory=list)
    resources: list = field(default_factory=list)
    prompts: list = field(default_factory=list)
    discovered_at: float | None = None
    error: str | None = None


def _error_json(kind: str, tool: str, detail: str) -> str:
    return json.dumps({"error": "MCP tool execution failed", "kind": kind, "tool": tool, "detail": detail})


class McpRegistry:
    """Cache of what each configured MCP server currently exposes.

    - ensure_fresh() discovers/refreshes when a server is undiscovered,
      unavailable, stale (older than ttl_seconds) or was flagged stale by a
      failed call, and connects only to *configured* servers.
    - status(server) distinguishes NOT_DISCOVERED / AVAILABLE / UNAVAILABLE /
      CONSENT_REQUIRED.
    """

    def __init__(self, servers, approved_servers=(), ttl_seconds: float = 300.0,
                 allowed_roots=(REPO_ROOT,), clock=time.monotonic, consent_callback=None):
        self.configs = [parse_server_entry(s, allowed_roots) for s in servers]
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self.consent_callback = consent_callback  # cfg -> bool; asked once per server
        self._approved = {_cfg_id(a) for a in approved_servers}
        self._denied: set[str] = set()
        self._entries = {c.id: _Entry() for c in self.configs}
        self._conns: dict[str, _Connection] = {}
        self._stale: set[str] = set()
        self._lock = threading.RLock()

    # -- consent -----------------------------------------------------------
    def approve(self, server) -> None:
        cid = _cfg_id(server)
        self._approved.add(cid)
        self._denied.discard(cid)

    def _consented(self, cfg: ServerConfig) -> bool:
        if not cfg.requires_consent or cfg.id in self._approved:
            return True
        if self.consent_callback is not None and cfg.id not in self._denied:
            if self.consent_callback(cfg):
                self._approved.add(cfg.id)
                return True
            self._denied.add(cfg.id)  # do not nag again until approve() is called
        return False

    # -- discovery ---------------------------------------------------------
    def status(self, server) -> str:
        return self._entries[_cfg_id(server)].status

    def statuses(self) -> dict:
        return {Path(k).name: e.status for k, e in self._entries.items()}

    def ensure_fresh(self, force: bool = False) -> None:
        with self._lock:
            for cfg in self.configs:
                entry = self._entries[cfg.id]
                stale = (
                    entry.discovered_at is None
                    or self._clock() - entry.discovered_at > self.ttl_seconds
                    or cfg.id in self._stale
                    or not entry.tools and entry.status == AVAILABLE
                )
                conn = self._conns.get(cfg.id)
                if force or entry.status in (NOT_DISCOVERED, UNAVAILABLE, CONSENT_REQUIRED) \
                        or stale or (conn is not None and not conn.alive):
                    self._refresh(cfg)

    def _connect(self, cfg: ServerConfig) -> _Connection:
        conn = self._conns.get(cfg.id)
        if conn is not None and conn.alive:
            return conn
        if conn is not None:
            conn.close()
        conn = _Connection(cfg).start()
        self._conns[cfg.id] = conn
        return conn

    def _refresh(self, cfg: ServerConfig) -> None:
        entry = self._entries[cfg.id]
        if not self._consented(cfg):
            entry.status, entry.error = CONSENT_REQUIRED, "user consent required before connecting"
            return
        try:
            conn = self._connect(cfg)
            tools = conn.request(lambda s: s.list_tools()).tools
            caps = conn.capabilities
            resources = prompts = []
            if getattr(caps, "resources", None):
                resources = conn.request(lambda s: s.list_resources()).resources
            if getattr(caps, "prompts", None):
                prompts = conn.request(lambda s: s.list_prompts()).prompts
        except Exception as exc:  # noqa: BLE001
            entry.status, entry.error = UNAVAILABLE, _describe(exc)
            entry.tools, entry.resources, entry.prompts = [], [], []
            return
        entry.tools = [
            {"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema}
            for t in tools
            if cfg.permitted_tools is None or t.name in cfg.permitted_tools
        ]
        entry.resources = [{"uri": str(r.uri), "name": r.name, "description": r.description or ""} for r in resources]
        entry.prompts = [{"name": p.name, "description": p.description or "",
                          "arguments": [a.name for a in (p.arguments or [])]} for p in prompts]
        entry.status, entry.error = AVAILABLE, None
        entry.discovered_at = self._clock()
        self._stale.discard(cfg.id)

    # -- views -------------------------------------------------------------
    def _owner_map(self) -> dict:
        owners = {}
        for cfg in self.configs:
            entry = self._entries[cfg.id]
            if entry.status != AVAILABLE:
                continue
            for tool in entry.tools:
                if tool["name"] in owners:
                    raise ValueError(f"Duplicate MCP tool name discovered: {tool['name']}")
                owners[tool["name"]] = (cfg, tool)
        return owners

    def tool_schemas(self) -> list:
        schemas = [
            {"type": "function", "function": {
                "name": name, "description": tool["description"], "parameters": tool["inputSchema"]}}
            for name, (_, tool) in self._owner_map().items()
        ]
        schemas.extend(self._aux_schemas())
        return schemas

    def tool_functions(self) -> dict:
        functions = {
            name: (lambda _n=name, **arguments: self.call_tool(_n, arguments))
            for name in self._owner_map()
        }
        if self._aux_schemas():
            functions[READ_RESOURCE_TOOL] = lambda **a: self.read_resource(**a)
            functions[GET_PROMPT_TOOL] = lambda **a: self.get_prompt(**a)
        return functions

    def _aux_schemas(self) -> list:
        resources = [r for e in self._entries.values() if e.status == AVAILABLE for r in e.resources]
        prompts = [p for e in self._entries.values() if e.status == AVAILABLE for p in e.prompts]
        schemas = []
        if resources:
            listing = "; ".join(f"{r['uri']} ({r['name']})" for r in resources)
            schemas.append({"type": "function", "function": {
                "name": READ_RESOURCE_TOOL,
                "description": f"Read an MCP resource by URI. Available: {listing}",
                "parameters": {"type": "object", "properties": {"uri": {"type": "string"}}, "required": ["uri"]},
            }})
        if prompts:
            listing = "; ".join(f"{p['name']}({', '.join(p['arguments'])})" for p in prompts)
            schemas.append({"type": "function", "function": {
                "name": GET_PROMPT_TOOL,
                "description": f"Fetch an MCP prompt template by name. Available: {listing}",
                "parameters": {"type": "object", "properties": {
                    "name": {"type": "string"}, "arguments": {"type": "object"}}, "required": ["name"]},
            }})
        return schemas

    def tool_names(self) -> list:
        return sorted(self._owner_map())

    def problems(self) -> dict:
        """Servers that are configured but not currently usable -> reason."""
        return {Path(k).name: f"{e.status}: {e.error}" for k, e in self._entries.items()
                if e.status in (UNAVAILABLE, CONSENT_REQUIRED)}

    def raise_if_unusable(self) -> None:
        """Raise a precise error when no server can supply any tool."""
        if self.tool_names():
            return
        if any(e.status == CONSENT_REQUIRED for e in self._entries.values()):
            raise McpConsentRequired(f"MCP consent required: {self.problems()}")
        raise McpServerUnavailable(f"No MCP tools available: {self.problems() or 'servers expose no tools'}")

    # -- execution ---------------------------------------------------------
    def validate_arguments(self, tool: dict, arguments: dict) -> str | None:
        schema = tool["inputSchema"] or {}
        problems = [e.message for e in Draft202012Validator(schema).iter_errors(arguments)]
        known = set((schema.get("properties") or {}))
        unknown = sorted(set(arguments) - known) if known or schema.get("type") == "object" else []
        if unknown:
            problems.append(f"unexpected argument(s): {', '.join(unknown)}")
        return "; ".join(problems) or None

    def call_tool(self, name: str, arguments: dict) -> str:
        try:
            cfg, tool = self._owner_map()[name]
        except KeyError:
            self._stale.update(self._entries)  # capability list may be out of date
            return _error_json("unknown_tool", name, "tool is not exposed by any available server")

        invalid = self.validate_arguments(tool, arguments)
        if invalid:
            return _error_json("invalid_arguments", name, invalid)

        _record_mcp_wire_event("client_to_server", f"Calling MCP tool: {name}",
                               {"method": "tools/call", "params": {"name": name, "arguments": arguments}})
        result = None
        for attempt in (1, 2):
            conn = None
            try:
                with self._lock:
                    conn = self._connect(cfg)  # reconnects if the previous one was marked dead
                result = conn.request(lambda s: s.call_tool(name, arguments=arguments))
                break
            except McpServerUnavailable as exc:
                # Retry exactly once, and only for a dead connection (the call
                # never completed), never for a timeout or a tool-side failure.
                if attempt == 1 and conn is not None and not conn.alive:
                    continue
                self._entries[cfg.id].status = UNAVAILABLE
                self._entries[cfg.id].error = str(exc)
                return _error_json("server_unavailable", name, str(exc))
            except Exception as exc:  # noqa: BLE001
                return _error_json("protocol_error", name, _describe(exc))

        texts = [i.text for i in result.content if hasattr(i, "text")]
        _record_mcp_wire_event("server_to_client", f"Tool execution response: {name}",
                               {"result": {"isError": result.isError, "content": texts}})
        if result.isError:
            detail = " ".join(texts) or "tool reported an error"
            if re.search(r"unknown tool", detail, re.IGNORECASE):
                self._stale.add(cfg.id)
            return _error_json("auth" if _AUTH_PATTERN.search(detail) else "tool_error", name, detail)
        return json.dumps({"content": texts})

    def read_resource(self, uri: str) -> str:
        for cfg in self.configs:
            entry = self._entries[cfg.id]
            if entry.status == AVAILABLE and any(r["uri"] == uri for r in entry.resources):
                try:
                    conn = self._connect(cfg)
                    result = conn.request(lambda s: s.read_resource(uri))
                except Exception as exc:  # noqa: BLE001
                    return _error_json("server_unavailable", READ_RESOURCE_TOOL, _describe(exc))
                return json.dumps({"content": [getattr(c, "text", None) for c in result.contents]})
        return _error_json("unknown_resource", READ_RESOURCE_TOOL, f"no available server exposes {uri}")

    def get_prompt(self, name: str, arguments: dict | None = None) -> str:
        for cfg in self.configs:
            entry = self._entries[cfg.id]
            if entry.status == AVAILABLE and any(p["name"] == name for p in entry.prompts):
                try:
                    conn = self._connect(cfg)
                    result = conn.request(lambda s: s.get_prompt(name, arguments or {}))
                except Exception as exc:  # noqa: BLE001
                    return _error_json("server_unavailable", GET_PROMPT_TOOL, _describe(exc))
                return json.dumps({"messages": [
                    {"role": m.role, "text": getattr(m.content, "text", None)} for m in result.messages]})
        return _error_json("unknown_prompt", GET_PROMPT_TOOL, f"no available server exposes prompt {name}")

    def close(self) -> None:
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()
        for entry in self._entries.values():
            entry.status = NOT_DISCOVERED
            entry.discovered_at = None


# --------------------------------------------------------------------------
# Backwards-compatible helpers
# --------------------------------------------------------------------------

def get_mcp_tools(server_script: str):
    """One-shot discovery of a single server's tools (opens and closes a session)."""
    registry = McpRegistry([server_script])
    try:
        registry.ensure_fresh()
        registry.raise_if_unusable()
        return list(registry._entries[registry.configs[0].id].tools)
    finally:
        registry.close()


def build_multi_mcp_tool_registry(server_scripts: list, **registry_kwargs):
    """Discover tools from the given servers and return (schemas, functions).
    The returned functions keep their connections alive via the registry."""
    registry = McpRegistry(server_scripts, **registry_kwargs)
    registry.ensure_fresh()
    registry.raise_if_unusable()
    return registry.tool_schemas(), registry.tool_functions()


def build_mcp_tool_registry(server_script: str):
    return build_multi_mcp_tool_registry([server_script])
