# wire.json — hand annotations

Raw JSON-RPC capture against the package-registry server (`agent/mcp_servers/package_server.py`),
taken by `agent/wire_capture.py`, which talks to the server's stdin/stdout directly (no MCP SDK
client in the loop) so every byte on the wire is visible. 6 messages, in order:

## 1. `initialize` request (client → server)
- `jsonrpc`: protocol version tag, always `"2.0"`.
- `id`: request id (`1`); the matching response echoes this id back.
- `method`: `"initialize"` — the first call of the MCP handshake.
- `params.protocolVersion`: MCP protocol version the client speaks.
- `params.capabilities`: client-side capability flags (empty — this client doesn't support sampling/roots).
- `params.clientInfo`: name/version of the connecting client, for the server's logs.

## 2. `initialize` response (server → client)
- `id`: `1`, matches the request.
- `result.protocolVersion`: version the server agreed to use.
- `result.capabilities`: what the server supports — `tools.listChanged: false` means it won't push
  tool-list-changed notifications; `resources`/`prompts` are declared but unused here.
- `result.serverInfo`: the server's self-reported name (`package-registry-server`) and version
  (`1.30.0`) — this is the "who wrote it" string DevRel would have put in their FastMCP app.

## 3. `notifications/initialized` (client → server)
- `method` only, no `id` — a one-way notification (no response expected), telling the server the
  handshake is complete and it's safe to start serving normal requests.

## 4. `tools/list` request (client → server)
- `id`: `2`. `method`: `"tools/list"`. `params`: empty — no filtering supported.

## 5. `tools/list` response (server → client)
- `result.tools`: array of tool descriptors, each with:
  - `name` — the identifier the model will use in a tool call.
  - `description` — the full docstring, sent to the model verbatim as part of the tool's
    definition. This is the "prompt" referred to in requirement 5: whatever is written here is
    what steers the model's tool choice and argument shape.
  - `inputSchema` — JSON Schema generated from the Python function signature.
  - `outputSchema` — JSON Schema for the return value (FastMCP-specific; not part of base MCP).

## 6. `tools/call` request (client → server)
- `id`: `3`. `params.name`: the exact tool name from `tools/list`. `params.arguments`: the
  argument object the model decided on, validated against `inputSchema` before this request is sent.

## 7. `tools/call` response (server → client)
- `result.content`: array of content blocks (here, one `type: "text"` block) — the tool's return
  value, serialized to a string, is what gets fed back into the model's next turn as a tool-result
  message.
- `result.structuredContent`: FastMCP's typed echo of the same data, validated against `outputSchema`.
- `result.isError`: `false` — if `true`, the model sees this as a failed tool call instead of data.

## Where the model call happens — and where it doesn't

**None of the 7 messages above involve the model.** They are pure JSON-RPC between the host's MCP
client and the `package_server.py` subprocess, exchanged entirely over stdio. The one and only LLM
call in this whole system happens in `agent/loop.py`'s `client.chat.completions.create(...)` —
a separate HTTP request to Groq, made by the host process after it already has the `tools/list`
schemas in hand, and again after a `tools/call` result comes back on the wire above; the MCP server
itself never sees the model's prompt, is never bound to it, and never constructs the model's final
answer — it only ever returns inert, serialized data.
