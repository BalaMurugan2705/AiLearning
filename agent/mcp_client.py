import asyncio
import sys
import os

from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_path = (
        Path(__file__).parent
        / "mcp_servers"
        / "docs_server.py"
    )
    project_root = Path(__file__).resolve().parent.parent

    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get(
        "PYTHONPATH", ""
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

            # MCP initialization handshake
            await session.initialize()

            print("Connected to documentation MCP server")

            # Discover available tools dynamically
            tools_result = await session.list_tools()

            for tool in tools_result.tools:
                print(f"Tool: {tool.name}")
                print(f"Description: {tool.description}")

            # Call the discovered MCP tool
            result = await session.call_tool(
                "search_documentation",
                arguments={
                    "query": "How does the existing API authentication work?",
                    "k": 3,
                },
            )

            print("\nMCP Tool Call Result:")
            for content in result.content:
                if hasattr(content, "text"):
                    print(content.text)


if __name__ == "__main__":
    asyncio.run(main())