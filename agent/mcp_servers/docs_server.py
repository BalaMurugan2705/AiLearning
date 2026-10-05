from mcp.server.fastmcp import FastMCP

from agent.tools import search_docs


# Create an MCP server
mcp = FastMCP("documentation-server")


@mcp.tool()
def search_documentation(query: str, k: int = 4) -> str:
    """
    Search the indexed GitHub REST API developer documentation for prose
    relevant to a natural-language question.

    Use this first for anything that is not about one specific endpoint's
    exact parameter shape -- explanations, "how does X work", or
    version-to-version behavior changes.

    This server only has documentation indexed for API versions
    2022-11-28 and 2025-06-01. If your query names a different version
    (e.g. 2026-01-01, v3, v4), the result will contain an "error" field
    instead of "results", naming the latest indexed version and the full
    list of known versions. Re-ask using one of those versions -- do not
    substitute a nearby version's docs and present them as if they apply
    to the version that was actually asked about.

    Args:
        query: The natural-language documentation question to search.
        k: Number of relevant chunks to return.
    """
    result = search_docs(query=query, k=k)

    return str(result)


if __name__ == "__main__":
    mcp.run(transport="stdio")