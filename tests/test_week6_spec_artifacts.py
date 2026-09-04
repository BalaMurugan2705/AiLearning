"""The three artifacts the deterministic assertions check against.

symbols.json is script-generated so it cannot drift from the corpus.
deprecations.json is hand-curated because the v2->v3 removals exist only as
prose in migrating-to-v3.md -- the backticked-symbol diff between the two
version trees yields exactly one v2-only symbol (RELAY_401).
"""
import json
from pathlib import Path

from eval.spec import load_specs
from eval.spec.build_symbols import extract_symbols

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "data" / "documents"


def test_extract_symbols_finds_error_codes_in_both_versions():
    result = extract_symbols(DOCS)
    assert result["symbols"]["RELAY_429"]["kind"] == "error_code"
    assert result["symbols"]["RELAY_429"]["versions"] == ["v2", "v3"]


def test_extract_symbols_records_a_v3_only_symbol_as_v3_only():
    result = extract_symbols(DOCS)
    assert result["symbols"]["AUTH_SCOPE_DENIED"]["versions"] == ["v3"]


def test_extract_symbols_records_the_one_v2_only_symbol():
    """RELAY_401 is the only v2-only backticked symbol in the whole corpus."""
    result = extract_symbols(DOCS)
    assert result["symbols"]["RELAY_401"]["versions"] == ["v2"]


def test_extract_symbols_captures_parameters_and_qualified_methods():
    result = extract_symbols(DOCS)
    assert result["symbols"]["retry_backoff_ms"]["kind"] == "parameter"
    assert "Client.send()" in result["symbols"]


def test_extract_symbols_excludes_python_builtins_and_bare_words():
    result = extract_symbols(DOCS)
    for noise in ("str", "int", "None", "True", "False", "message", "id"):
        assert noise not in result["symbols"], f"{noise} would cause false failures"


def test_openapi_contains_the_one_real_path_and_nothing_invented():
    spec = json.loads((REPO / "eval/spec/relay_openapi.json").read_text())
    assert list(spec["paths"]) == ["/v3/auth/token"]
    assert "post" in spec["paths"]["/v3/auth/token"]


def test_every_deprecation_entry_is_traceable_and_actionable():
    entries = json.loads((REPO / "eval/spec/deprecations.json").read_text())
    assert len(entries) >= 5
    for entry in entries:
        assert entry["id"]
        assert entry["match"], "needs a regex to detect the deprecated thing"
        assert entry["migration_signals"], "needs phrases that count as a migration note"
        assert entry["source"], "must cite the doc it was derived from"


def test_load_specs_returns_all_three():
    specs = load_specs()
    assert "RELAY_429" in specs["symbols"]
    assert "/v3/auth/token" in specs["openapi"]["paths"]
    assert len(specs["deprecations"]) >= 5
