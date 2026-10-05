"""One-off script: report tools/list output before and after adding the
package-registry server, taken live from the MCP servers -- not from notes."""
import json
from pathlib import Path

from agent.mcp_adapter import get_mcp_tools

PROJECT_ROOT = Path(__file__).resolve().parent

with open(PROJECT_ROOT / "mcp_config.json", encoding="utf-8") as f:
    all_servers = [str(PROJECT_ROOT / p) for p in json.load(f)["mcp_servers"]]

docs_only = [s for s in all_servers if "docs_server" in s]

before_tools = []
for server in docs_only:
    before_tools.extend(get_mcp_tools(server))

after_tools = []
for server in all_servers:
    after_tools.extend(get_mcp_tools(server))

report = {
    "before": {
        "servers": docs_only,
        "count": len(before_tools),
        "names": [t["name"] for t in before_tools],
    },
    "after": {
        "servers": all_servers,
        "count": len(after_tools),
        "names": [t["name"] for t in after_tools],
    },
}

Path("tool_count.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
