"""Tiny MCP server used by tests. Setting MCP_PROBE_EXTRA_FLAG to an existing
file path makes it expose an extra tool, simulating a newly added capability."""
import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("probe")


@mcp.tool()
def echo(text: str, times: int = 1) -> str:
    """Echo text back."""
    return text * times


@mcp.tool()
def boom(x: str) -> str:
    """Always fails with an auth-style error."""
    raise PermissionError("401 Unauthorized: token expired")


@mcp.tool()
def leaked_secret() -> str:
    """Report whether the parent's secret reached this subprocess."""
    return os.environ.get("SECRET_TOKEN_FOR_TEST", "absent")


@mcp.resource("probe://note")
def note() -> str:
    """A static note."""
    return "resource-body"


@mcp.prompt()
def greet(name: str) -> str:
    """Greeting prompt."""
    return f"hello {name}"


flag = os.environ.get("MCP_PROBE_EXTRA_FLAG")
if flag and os.path.exists(flag):
    @mcp.tool()
    def brand_new_tool(x: int) -> str:
        """Added after startup."""
        return f"new:{x}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
