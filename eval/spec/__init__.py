"""Loader for the three artifacts the deterministic assertions check against."""
import json
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parent


def load_specs(base: Path | None = None) -> dict:
    base = base or SPEC_DIR
    symbols = json.loads((base / "symbols.json").read_text(encoding="utf-8"))
    return {
        "symbols": symbols["symbols"],
        "openapi": json.loads((base / "relay_openapi.json").read_text(encoding="utf-8")),
        "deprecations": json.loads((base / "deprecations.json").read_text(encoding="utf-8")),
    }
