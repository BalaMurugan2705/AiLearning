import asyncio
import os
import sys
import json
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from datetime import datetime, timezone

# Record MCP protocol messages to a separate JSON file.
# This keeps raw MCP traffic distinct from host_tool_calls.json.
def _record_mcp_wire_event(direction: str, annotation: str, message: dict):
    # Read the capture destination from the environment, or use a default.
    capture_path = os.environ.get(
        "MCP_WIRE_CAPTURE",
        "wire.json",
    )

    # Build one structured record for the JSON-RPC message.
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "annotation": annotation,
        "message": message,
    }

    # Load previous records so each event appends to the existing trace.
    try:
        with open(capture_path, "r", encoding="utf-8") as file:
            events = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        # Start a fresh list if the file does not exist or is empty.
        events = []

    # Append the new protocol event.
    events.append(event)

    # Save the complete trace in readable JSON format.
    with open(capture_path, "w", encoding="utf-8") as file:
        json.dump(events, file, indent=2)

async def discover_mcp_tools(server_script: str):
    """Connect to an MCP server and discover its tools."""

    project_root = Path(__file__).resolve().parent.parent

    server_path = Path(server_script).resolve()

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(project_root)
        + os.pathsep
        + env.get("PYTHONPATH", "")
    )

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
        env=env,
        cwd=str(project_root),
    )

    async with stdio_client(server_params) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            result = await session.list_tools()

            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema,
                }
                for tool in result.tools
            ]


def get_mcp_tools(server_script: str):
    """Synchronous wrapper for MCP tool discovery."""

    return asyncio.run(
        discover_mcp_tools(server_script)
    )
async def call_mcp_tool(
    server_script: str,
    tool_name: str,
    arguments: dict,
):
    """Execute a tool on an MCP server."""

    project_root = Path(__file__).resolve().parent.parent
    server_path = Path(server_script).resolve()

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(project_root)
        + os.pathsep
        + env.get("PYTHONPATH", "")
    )

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
        env=env,
        cwd=str(project_root),
    )

    async with stdio_client(server_params) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            # Initialize the MCP session and negotiate protocol capabilities.
            await session.initialize()

            # Record the initialization as an SDK-level event.
            _record_mcp_wire_event(
                direction="client_to_server",
                annotation="MCP session initialized; SDK handles the handshake",
                message={
                    "method": "initialize",
                    "server": str(server_path),
                },
            )

            # Record the requested tool and its arguments before execution.
            _record_mcp_wire_event(
                direction="client_to_server",
                annotation=f"Calling MCP tool: {tool_name}",
                message={
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                },
            )

            # Execute the tool through the MCP SDK.
            result = await session.call_tool(
                tool_name,
                arguments=arguments,
            )

            # Record the returned tool result for debugging and trace analysis.
            _record_mcp_wire_event(
                direction="server_to_client",
                annotation=f"Tool execution response: {tool_name}",
                message={
                    "result": {
                        "isError": result.isError,
                        "content": [
                            item.text
                            for item in result.content
                            if hasattr(item, "text")
                        ],
                    },
                },
            )

            # Return the original SDK result so existing agent behavior is preserved.
            return result


def execute_mcp_tool(
    server_script: str,
    tool_name: str,
    arguments: dict,
):
    """Synchronous wrapper for MCP tool execution."""

    return asyncio.run(
        call_mcp_tool(
            server_script,
            tool_name,
            arguments,
        )
    )
def build_mcp_tool_registry(server_script: str):
    """
    Discover MCP tools and convert them into
    Groq-compatible schemas and callable functions.
    """

    discovered_tools = get_mcp_tools(server_script)

    tool_schemas = []
    tool_functions = {}

    for tool in discovered_tools:
        name = tool["name"]

        # Convert MCP tool schema to Groq format
        tool_schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool["description"],
                "parameters": tool["inputSchema"],
            },
        })

        # Create a callable function for the agent loop
        def make_tool_function(tool_name):
            def call_tool_function(**arguments):
                result = execute_mcp_tool(
                    server_script=server_script,
                    tool_name=tool_name,
                    arguments=arguments,
                )

                if result.isError:
                    return json.dumps({
                        "error": "MCP tool execution failed",
                        "tool": tool_name,
                    })

                return json.dumps({
                    "content": [
                        item.text
                        for item in result.content
                        if hasattr(item, "text")
                    ]
                })

            return call_tool_function

        tool_functions[name] = make_tool_function(name)

    return tool_schemas, tool_functions

def build_multi_mcp_tool_registry(server_scripts: list[str]):
    """
    Discover tools from multiple MCP servers and combine them
    into one registry that the LLM agent can use.
    """

    # Store all discovered tool schemas for the LLM.
    combined_schemas = []

    # Store callable functions so the agent can execute each tool.
    combined_functions = {}

    # Connect to each configured server and discover its tools.
    for server_script in server_scripts:
        server_schemas, server_functions = build_mcp_tool_registry(
            server_script
        )

        # Add this server's tools to the shared LLM tool list.
        combined_schemas.extend(server_schemas)

        # Merge the callable functions into the shared registry.
        # This allows the agent loop to dispatch tools by name.
        for name, function in server_functions.items():
            if name in combined_functions:
                # Prevent ambiguous dispatch if two servers expose
                # the same tool name.
                raise ValueError(
                    f"Duplicate MCP tool name discovered: {name}"
                )

            combined_functions[name] = function

    # Return one unified registry for the multi-server agent.
    return combined_schemas, combined_functions