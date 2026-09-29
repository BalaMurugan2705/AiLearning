
# Import asyncio so we can run the raw MCP capture from async code.
import asyncio

# Import json to serialize and parse newline-delimited JSON-RPC messages.
import json

# Import os and sys to launch the MCP server with the current Python environment.
import os
import sys

# Import subprocess to communicate with the MCP server over raw stdin/stdout.
import subprocess

# Import Path to resolve the project and server file paths reliably.
from pathlib import Path

# Import datetime to timestamp each captured protocol message.
from datetime import datetime, timezone

# Import the MCP SDK's supported protocol version instead of hardcoding it.
from mcp.types import LATEST_PROTOCOL_VERSION


async def capture_mcp_wire(
    server_script: str,
    tool_name: str,
    arguments: dict,
    output_file: str = "wire.json",
):
    # Resolve the project root so the server can import the agent package.
    project_root = Path(__file__).resolve().parent.parent

    # Resolve the server script to an absolute path.
    server_path = Path(server_script).resolve()

    # Copy the current environment so the child process inherits dependencies.
    env = os.environ.copy()

    # Add the project root to PYTHONPATH so imports work in the child process.
    env["PYTHONPATH"] = (
        str(project_root)
        + os.pathsep
        + env.get("PYTHONPATH", "")
    )

    # Start the MCP server with pipes so we can capture raw JSON-RPC lines.
    process = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(project_root),
        env=env,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )

    # Keep all captured messages in memory before writing the final JSON file.
    captured_messages = []

    # Use a counter to assign unique JSON-RPC request IDs.
    request_id = 0

    def record_message(direction, annotation, message, raw_line=None):
        # Store both the parsed JSON object and original line for inspection.
        captured_messages.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": direction,
            "annotation": annotation,
            "raw_line": raw_line,
            "message": message,
        })

    def send_message(message, annotation):
        # Serialize the JSON-RPC message as one JSON line.
        raw_line = json.dumps(message, separators=(",", ":"))

        # Write the exact line to the server's stdin.
        process.stdin.write(raw_line + "\n")
        process.stdin.flush()

        # Record the outbound message after sending it.
        record_message(
            direction="client_to_server",
            annotation=annotation,
            message=message,
            raw_line=raw_line,
        )

    def read_response(expected_id, annotation):
        # Read server output until the matching JSON-RPC response arrives.
        while True:
            raw_line = process.stdout.readline()

            # Stop if the server closes stdout unexpectedly.
            if not raw_line:
                raise RuntimeError(
                    f"MCP server exited before responding to request {expected_id}"
                )

            # Parse the raw JSON-RPC line from the server.
            message = json.loads(raw_line)

            # Record every server message, including notifications.
            record_message(
                direction="server_to_client",
                annotation=annotation,
                message=message,
                raw_line=raw_line.rstrip("\n"),
            )

            # Return only the response matching the requested ID.
            if message.get("id") == expected_id:
                return message

    try:
        # Step 1: Send the MCP initialize request.
        request_id += 1
        initialize_id = request_id

        send_message({
            "jsonrpc": "2.0",
            "id": initialize_id,
            "method": "initialize",
            "params": {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "wire-capture-client",
                    "version": "1.0.0",
                },
            },
        }, "MCP initialization handshake")

        # Read the server's initialize response.
        initialize_response = read_response(
            initialize_id,
            "MCP initialization response",
        )

        # Stop if the server returned a JSON-RPC error.
        if "error" in initialize_response:
            raise RuntimeError(
                f"Initialize failed: {initialize_response['error']}"
            )

        # Step 2: Notify the server that initialization is complete.
        send_message({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }, "Initialization-complete notification")

        # Step 3: Request the list of tools exposed by the server.
        request_id += 1
        list_id = request_id

        send_message({
            "jsonrpc": "2.0",
            "id": list_id,
            "method": "tools/list",
            "params": {},
        }, "Discovering server tools")

        # Read the tool discovery response.
        list_response = read_response(
            list_id,
            "Tool discovery response",
        )

        # Stop if the server returned an error for tools/list.
        if "error" in list_response:
            raise RuntimeError(
                f"tools/list failed: {list_response['error']}"
            )

        # Step 4: Call the requested MCP tool.
        request_id += 1
        call_id = request_id

        send_message({
            "jsonrpc": "2.0",
            "id": call_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }, f"Calling MCP tool: {tool_name}")

        # Read the tool execution response.
        call_response = read_response(
            call_id,
            f"Tool execution response: {tool_name}",
        )

        # Save the captured messages as formatted JSON for review.
        output_path = Path(output_file).resolve()
        output_path.write_text(
            json.dumps(captured_messages, indent=2),
            encoding="utf-8",
        )

        # Return the tool response so the caller can inspect it.
        return call_response

    finally:
        # Close pipes and stop the child server to avoid orphan processes.
        if process.stdin:
            process.stdin.close()

        # Terminate the server after capture is complete.
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    # Run one example capture against the package registry MCP server.
    result = asyncio.run(
        capture_mcp_wire(
            server_script="agent/mcp_servers/package_server.py",
            tool_name="get_package_api_spec",
            arguments={
                "endpoint": "create_issue",
                "api_version": "2025-06-01",
            },
        )
    )

    # Print the response so we can confirm the tool call completed.
    print(json.dumps(result, indent=2))