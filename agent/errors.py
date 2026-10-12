class NonRetryableError(Exception):
    """A failure that retrying cannot fix (policy, consent, bad config)."""


class McpPolicyError(NonRetryableError):
    """A configured MCP server violates the launch policy."""


class McpConsentRequired(NonRetryableError):
    """A configured MCP server needs user consent before it is connected."""


class McpServerUnavailable(Exception):
    """A configured MCP server could not be started or reached (retryable)."""
