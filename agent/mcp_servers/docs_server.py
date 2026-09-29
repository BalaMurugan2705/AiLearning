from mcp.server.fastmcp import FastMCP

from agent.tools import search_docs


# Create an MCP server
mcp = FastMCP("documentation-server")


@mcp.tool()
def search_documentation(query: str, k: int = 4) -> str:
    """
    Search the indexed developer documentation.

    Use this tool to find relevant documentation
    for a natural-language technical question.

    Args:
        query: The documentation question to search.
        k: Number of relevant chunks to return.
    """
    result = search_docs(query=query, k=k)

    return str(result)


if __name__ == "__main__":
    mcp.run(transport="stdio")