1. Tool execution failures: MCP tools may time out or return errors; the host must return recoverable error results to the agent.
2. Tool security: Validate tool arguments and enforce authorization before executing tools.
3. Data exposure: Avoid logging secrets, credentials, or sensitive tool arguments in traces and wire captures.
4. Resource limits: Enforce iteration, token, cost, and execution-time budgets to prevent runaway agent loops.
5. External dependencies: MCP servers and third-party APIs may be unavailable or return stale data; handle failures and validate results.
