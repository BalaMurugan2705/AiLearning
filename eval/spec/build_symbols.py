"""Corpus -> eval/spec/symbols.json.

Generated rather than hand-listed so the assertion's authority cannot drift
from the documents it claims to describe. Each symbol records which SDK
versions it appears in, which assertion A5 reuses to reason about v2-only
things.

Only distinctive SDK-shaped tokens are collected. Python builtins and bare
prose words the corpus happens to backtick (`str`, `int`, `message`) are
deliberately excluded: including them would make assertion A2 fail on
ordinary English.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

# Tokens that are real Python or plain nouns, not SDK symbols. A2 must never
# examine these, so they never enter the table in the first place.
STOPLIST = {
    "str", "int", "float", "bool", "dict", "list", "None", "True", "False",
    "id", "code", "message", "channel", "attempts", "items", "read", "send",
    "stream", "admin", "force", "cursor", "direction", "exhausted", "retryable",
    "deduplicated", "has_more", "accepted_at",
}

ERROR_CODE_RE = re.compile(r"\b(RELAY_\d{3}|AUTH_[A-Z_]{3,})\b")
CLASS_RE = re.compile(r"\b(Relay[A-Z]\w*|Signature[A-Z]\w*|Stream[A-Z]\w*|[A-Z]\w*Cache)\b")
METHOD_RE = re.compile(r"\b(Client\.\w+\(\))")
# At least one underscore is required, which is what keeps single prose words
# out without needing to enumerate them.
PARAM_RE = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")

VERSION_DIRS = ("v2", "v3")


def _add(table: dict, name: str, kind: str, version: str, source: str) -> None:
    if name in STOPLIST:
        return
    entry = table.setdefault(name, {"kind": kind, "versions": [], "sources": []})
    if version not in entry["versions"]:
        entry["versions"].append(version)
    if source not in entry["sources"]:
        entry["sources"].append(source)


def extract_symbols(docs_dir: Path) -> dict:
    table: dict = {}
    for version in VERSION_DIRS:
        version_dir = docs_dir / version
        for path in sorted(version_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            source = f"{version}/{path.name}"
            for name in ERROR_CODE_RE.findall(text):
                _add(table, name, "error_code", version, source)
            for name in CLASS_RE.findall(text):
                _add(table, name, "class", version, source)
            for name in METHOD_RE.findall(text):
                _add(table, name, "method", version, source)
            for name in PARAM_RE.findall(text):
                _add(table, name, "parameter", version, source)

    for entry in table.values():
        entry["versions"].sort()

    return {
        "generated_by": "eval/spec/build_symbols.py",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbols": dict(sorted(table.items())),
    }


def main() -> None:
    base = Path(__file__).resolve().parent
    docs = base.parent.parent / "data" / "documents"
    result = extract_symbols(docs)
    out = base / "symbols.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} with {len(result['symbols'])} symbols")


if __name__ == "__main__":
    main()
