import json
from pathlib import Path

_SPEC_DIR = Path(__file__).resolve().parent / "data"

with open(_SPEC_DIR / "github_openapi.json") as f:
    _OPENAPI = json.load(f)

with open(_SPEC_DIR / "deprecations.json") as f:
    _DEPRECATIONS = json.load(f)

ENDPOINT_NAMES: list[str] = sorted(_OPENAPI["endpoints"].keys())
API_VERSIONS: list[str] = _OPENAPI["api_versions"]


def get_endpoint_spec(endpoint: str, api_version: str) -> dict | None:
    endpoint_data = _OPENAPI["endpoints"].get(endpoint)
    if endpoint_data is None:
        return None
    version_data = endpoint_data["versions"].get(api_version)
    if version_data is None:
        return None
    return {
        "endpoint": endpoint,
        "method": endpoint_data["method"],
        "path": endpoint_data["path"],
        "api_version": api_version,
        "params": version_data["params"],
        "x_source": version_data["x_source"],
    }


def find_deprecation(endpoint: str, api_version: str) -> dict | None:
    for entry in _DEPRECATIONS:
        if entry["endpoint"] == endpoint and entry["deprecated_in"] == api_version:
            return entry
    return None
