import json
import re

from agent.corpus import get_pipeline, search_docs_raw
from agent.spec import API_VERSIONS, ENDPOINT_NAMES, find_deprecation, get_endpoint_spec

_pipeline = None

# GitHub API versions look like YYYY-MM-DD. Catching this in the query lets
# us tell "asked about a version we don't have" apart from "asked something
# broad" -- without it, search_docs silently hands back the nearest
# semantic match for a version that was never indexed, and the model has no
# way to know the chunk it got doesn't actually apply to that version.
_VERSION_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _get_or_build_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = get_pipeline()
    return _pipeline


def search_docs(query: str, k: int = 4) -> str:
    requested_versions = set(_VERSION_PATTERN.findall(query))
    unknown_versions = requested_versions - set(API_VERSIONS)
    if unknown_versions:
        return json.dumps({
            "results": [],
            "error": (
                f"No documentation indexed for API version(s) "
                f"{', '.join(sorted(unknown_versions))}. Latest indexed "
                f"version is {max(API_VERSIONS)}. Known indexed versions: "
                f"{', '.join(API_VERSIONS)}. Re-ask using one of the known "
                "versions -- do not assume a nearby version's docs apply."
            ),
        })

    results = search_docs_raw(_get_or_build_pipeline(), query, k=k)
    trimmed = [
        {"source_file": r["metadata"].get("source_file", "unknown"), "text": r["text"][:500]}
        for r in results
    ]
    return json.dumps({"results": trimmed})


def get_openapi_spec(endpoint: str, api_version: str) -> str:
    spec = get_endpoint_spec(endpoint, api_version)
    if spec is None:
        return json.dumps(
            {"error": f"No spec for endpoint={endpoint!r} api_version={api_version!r}.",
             "known_endpoints": ENDPOINT_NAMES}
        )
    return json.dumps(spec)


def check_deprecation(endpoint: str, api_version: str) -> str:
    entry = find_deprecation(endpoint, api_version)
    if entry is None:
        return json.dumps(
            {"endpoint": endpoint, "api_version": api_version, "deprecated": False,
             "detail": "No deprecated fields recorded for this endpoint at this API version."}
        )
    return json.dumps({"endpoint": endpoint, "api_version": api_version, "deprecated": True, **entry})


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search the indexed developer documentation for text relevant to a "
                "natural-language question. Use this first for anything that is not "
                "about one specific endpoint's exact parameters or deprecation status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The natural-language search query."},
                    "k": {"type": "integer", "description": "How many chunks to return.", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_openapi_spec",
            "description": (
                "Return the exact method, path, and parameter list for one named "
                "GitHub endpoint at one specific API version. Use this only when you "
                "already know the endpoint name and need its precise parameter shape "
                "-- not for open-ended search, and not to check whether something is "
                "deprecated (use check_deprecation for that)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "enum": ENDPOINT_NAMES, "description": "The endpoint identifier, e.g. 'create_issue'."},
                    "api_version": {"type": "string", "enum": API_VERSIONS, "description": "Which API version's parameter shape to return."},
                },
                "required": ["endpoint", "api_version"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_deprecation",
            "description": (
                "Report whether a named endpoint has anything deprecated as of one "
                "specific API version, and what replaces it. Use this only to check "
                "deprecation status -- not to fetch the full parameter list (use "
                "get_openapi_spec instead) and not to search prose documentation "
                "(use search_docs instead)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "enum": ENDPOINT_NAMES, "description": "The endpoint identifier, e.g. 'create_issue'."},
                    "api_version": {"type": "string", "enum": API_VERSIONS, "description": "Which API version to check deprecation status against."},
                },
                "required": ["endpoint", "api_version"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "search_docs": search_docs,
    "get_openapi_spec": get_openapi_spec,
    "check_deprecation": check_deprecation,
}


def call_tool(name: str, arguments: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return fn(**arguments)
# Tools available to the Research Agent
RESEARCH_TOOL_SCHEMAS = [
    TOOL_SCHEMAS[0],  # search_docs
]

RESEARCH_TOOL_FUNCTIONS = {
    "search_docs": search_docs,
}


# Tools available to the Package Agent
PACKAGE_TOOL_SCHEMAS = [
    TOOL_SCHEMAS[1],  # get_openapi_spec
    TOOL_SCHEMAS[2],  # check_deprecation
]

PACKAGE_TOOL_FUNCTIONS = {
    "get_openapi_spec": get_openapi_spec,
    "check_deprecation": check_deprecation,
}