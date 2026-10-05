# FastMCP lets us expose existing Python functions as MCP tools.
from mcp.server.fastmcp import FastMCP

# Reuse the existing package functions so MCP and local agents
# return the same data without duplicating business logic.
from agent.tools import get_openapi_spec, check_deprecation


# Create a separate MCP server so package tools can be discovered
# independently from the documentation server.
mcp = FastMCP("package-registry-server")


@mcp.tool()
def get_package_api_spec(endpoint: str, api_version: str) -> str:
    """
    Return the exact API endpoint specification for a given version.

    Args:
        endpoint: The endpoint identifier, such as create_issue.
        api_version: The API version to retrieve.
    """
    # Delegate to the existing implementation to preserve its behavior.
    return get_openapi_spec(
        endpoint=endpoint,
        api_version=api_version,
    )


@mcp.tool()
def check_package_deprecation(endpoint: str, api_version: str) -> str:
    """
    Identify deprecated or removed fields for a specific API endpoint
    and API version.

    Use this tool when the user asks whether an API field is deprecated,
    which fields should be replaced, or whether an endpoint has
    version-specific deprecation changes.

    Do not use this tool to retrieve the complete endpoint schema.
    Use get_package_api_spec for endpoint parameters, types, and
    required fields.

    Args:
        endpoint: Exact endpoint identifier, such as create_issue.
        api_version: API version to check, such as 2025-06-01.

    Returns:
        Deprecation information for the requested endpoint and version.
    """
    # Reuse the existing deprecation implementation to preserve behavior.
    return check_deprecation(
        endpoint=endpoint,
        api_version=api_version,
    )
# Start the server over stdio so an MCP client can launch and communicate
# with it as a subprocess using the standard MCP protocol.
if __name__ == "__main__":
    mcp.run(transport="stdio")