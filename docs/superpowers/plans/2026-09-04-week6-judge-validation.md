# Week 6 Judge Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the docs-answer LLM judge against 25 blind human labels, move five assertable criteria out of the judge into deterministic code checks, and move the human-agreement figure with committed evidence of the ordering.

**Architecture:** A new `eval/week6/` package scores a *frozen* 25-answer snapshot. Five pure-Python assertions replace five of `judge_v0`'s six criteria, leaving `judge_v1` with one binary criterion. Human labels are committed to git before the judge may run — enforced in code by a guard that reads `git log` and refuses on uncommitted labels, and proven afterwards because each judge run embeds the labels' commit hash and sha256. `judge_v2` adds two of `judge_v1`'s own disagreements as few-shot examples, and agreement is re-measured over the same frozen answers.

**Tech Stack:** Python 3.14 (repo venv), stdlib only for the new code (`ast`, `re`, `json`, `hashlib`, `subprocess`, `argparse`), `groq` for the judge call, `pytest` for tests. **No new dependencies.**

**Spec:** `docs/superpowers/specs/2026-09-03-week6-judge-validation-design.md`

## Global Constraints

- **No new dependencies.** Everything new is stdlib plus the already-installed `groq`.
- **Answers are frozen.** `eval/raw/answers_25.json` is generated once by `snapshot.py`. `run.py` re-scores it and never regenerates it.
- **Labels are immutable after commit C2.** `eval/week6/labels_25.json` is never edited once committed. Task 13's test enforces this.
- **Judge model differs from the answering model.** Answers: `openai/gpt-oss-120b` (`GROQ_MODEL` default). Judge: `llama-3.3-70b-versatile` (`JUDGE_MODEL`), temperature `0`.
- **`skipped` is never `pass`.** An assertion that does not apply returns status `"skipped"`. Only `"fail"` fails a case.
- **Mode tags are exactly these five strings**, copied verbatim from `results/week5/taxonomy.md`: `citation-format`, `version-ambiguity`, `cross-product-bleed`, `unexplained-refusal`, `clean`.
- **Pass rate is always reported per mode**, never as a single pooled headline number.
- **Counts to report:** 5 deterministic assertions vs 1 judged criterion, down from 6 judged criteria in `judge_v0`.
- **Every LLM-calling function takes an injectable `call_fn`** so tests never hit the network.
- **Do not touch `rag/generator.py:38` `_CITATION_RE`.** The Week-5 citation fix is explicitly out of scope (spec §2); landing it would invalidate the frozen snapshot the labels describe.
- **Style:** match the existing `eval/` modules — module docstring explaining *why*, comments that justify non-obvious decisions, test names that read as sentences.

---

## File Structure

**New — spec artifacts (the authority the assertions check against):**
- `eval/spec/__init__.py` — `load_specs()`, the single loader every consumer uses
- `eval/spec/build_symbols.py` — generates `symbols.json` from the corpus
- `eval/spec/symbols.json` — generated; symbol → kind, versions, sources
- `eval/spec/relay_openapi.json` — hand-written, one real path, derived from `v3/auth.md:15`
- `eval/spec/deprecations.json` — hand-curated from `v2/migrating-to-v3.md`, each entry citing its source

**New — the week 6 harness:**
- `eval/week6/__init__.py`
- `eval/week6/assertions.py` — A1–A5, pure functions, no I/O
- `eval/week6/criterion.py` — reads the single criterion out of `judge_v1.txt`
- `eval/week6/build_cases.py` — lifts replay parameters out of `traces.jsonl`
- `eval/week6/cases.jsonl` — the 25 mode-tagged cases
- `eval/week6/snapshot.py` — generates the frozen answer set
- `eval/week6/judge.py` — prompt runner + ordering guard
- `eval/week6/agreement.py` — raw agreement, confusion matrix, Cohen's kappa
- `eval/week6/label.py` — blind labeling CLI
- `eval/week6/report.py` — renders `results/week6-results.md`
- `eval/week6/run.py` — the one command
- `eval/week6/labels_25.json` — your labels (produced in Task 12)

**New — prompts and write-ups:**
- `results/week6/judge_v0.txt`, `judge_v1.txt`, `judge_v2.txt`
- `results/week6/prediction.txt`, `results/week6/disagreements.md`
- `results/week6-results.md` — generated

**New — tests:**
- `tests/test_week6_spec_artifacts.py`, `test_week6_assertions.py`, `test_week6_cases.py`, `test_week6_judge_prompts.py`, `test_week6_snapshot.py`, `test_week6_ordering.py`, `test_week6_agreement.py`, `test_week6_label.py`, `test_week6_run.py`

**Modified:**
- `rag/config.py` — add `JUDGE_MODEL`
- `rag/generator.py` — add optional `model` parameter to `answer_question()` (backwards compatible)
- `README.md` — document the week 6 command

---

### Task 1: Spec artifacts

**Files:**
- Create: `eval/spec/__init__.py`
- Create: `eval/spec/build_symbols.py`
- Create: `eval/spec/relay_openapi.json`
- Create: `eval/spec/deprecations.json`
- Generate: `eval/spec/symbols.json`
- Test: `tests/test_week6_spec_artifacts.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `eval.spec.build_symbols.extract_symbols(docs_dir: Path) -> dict` returning `{"generated_by": str, "symbols": {name: {"kind": str, "versions": list[str], "sources": list[str]}}}`
  - `eval.spec.load_specs(base: Path | None = None) -> dict` returning `{"symbols": dict, "openapi": dict, "deprecations": list[dict]}` where `symbols` is the inner `{name: {...}}` map

- [ ] **Step 1: Write the failing test**

Create `tests/test_week6_spec_artifacts.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_spec_artifacts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.spec'`

- [ ] **Step 3: Write the symbol extractor**

Create `eval/spec/build_symbols.py`:

```python
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
```

- [ ] **Step 4: Write the loader**

Create `eval/spec/__init__.py`:

```python
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
```

- [ ] **Step 5: Write the OpenAPI spec**

Create `eval/spec/relay_openapi.json`. It contains exactly one path because
exactly one endpoint path exists in the entire corpus — padding it with
invented paths would give assertion A3 a fabricated authority, which is worse
than a narrow one:

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Relay HTTP API (documented surface only)",
    "version": "v3",
    "description": "Derived strictly from the indexed corpus. The only endpoint path stated anywhere in data/documents is POST /v3/auth/token (data/documents/v3/auth.md:15). No path here was invented: assertion A3 exists to catch fabricated endpoints, so its authority must itself be traceable to a documented line."
  },
  "paths": {
    "/v3/auth/token": {
      "post": {
        "summary": "Exchange a long-lived API key for a short-lived bearer token.",
        "x-source": "data/documents/v3/auth.md:15"
      }
    }
  }
}
```

- [ ] **Step 6: Write the deprecations list**

Create `eval/spec/deprecations.json`. Hand-curated, because the removals are
prose rather than symbols; every entry cites the line it came from:

```json
[
  {
    "id": "relay-401-error-code",
    "label": "RELAY_401",
    "kind": "error_code",
    "match": "\\bRELAY_401\\b",
    "replacement": "AUTH_TOKEN_EXPIRED / AUTH_SCOPE_DENIED",
    "migration_signals": ["AUTH_TOKEN_EXPIRED", "AUTH_SCOPE_DENIED", "v2 only", "not in v3", "replaced"],
    "source": "data/documents/v2/errors.md vs data/documents/v3/errors.md"
  },
  {
    "id": "offset-pagination",
    "label": "offset pagination",
    "kind": "pagination",
    "match": "\\b(page_offset|offset=|offset pagination|page offset)\\b",
    "replacement": "next_cursor / from_cursor",
    "migration_signals": ["next_cursor", "from_cursor", "cursor", "removed in v3", "no longer"],
    "source": "data/documents/v2/migrating-to-v3.md ('Offset pagination was removed entirely')"
  },
  {
    "id": "two-segment-channel",
    "label": "two-segment channel org/topic",
    "kind": "identifier_format",
    "match": "\\borg/topic\\b",
    "replacement": "org/team/topic",
    "migration_signals": ["org/team/topic", "three segment", "gained a segment", "v3 rejects", "RELAY_400"],
    "source": "data/documents/v2/migrating-to-v3.md ('A v2 channel org/topic becomes org/team/topic in v3')"
  },
  {
    "id": "long-lived-key-per-request",
    "label": "long-lived API key sent on every request",
    "kind": "auth_pattern",
    "match": "\\b(long-lived key|long-lived api key|key on every request)\\b",
    "replacement": "bearer token minted via POST /v3/auth/token",
    "migration_signals": ["bearer token", "/v3/auth/token", "token exchange", "short-lived", "v3 instead"],
    "source": "data/documents/v2/migrating-to-v3.md + data/documents/v2/auth.md"
  },
  {
    "id": "v2-fixed-delay-retry",
    "label": "v2 fixed-delay retry defaults (500 ms, 3 attempts)",
    "kind": "defaults",
    "match": "\\b(500\\s?ms|three attempts 500|fixed-delay)\\b",
    "replacement": "retry_backoff_ms=2000 with retry_backoff_factor over 4 attempts",
    "migration_signals": ["2000", "exponential", "retry_backoff_factor", "v2", "re-derive", "changed in v3"],
    "source": "data/documents/v2/migrating-to-v3.md + data/documents/v2/CHANGELOG.md (2.5.0)"
  },
  {
    "id": "v2-webhook-signatures",
    "label": "v2 webhook signatures",
    "kind": "signing_scheme",
    "match": "\\bv2 (webhook )?signature",
    "replacement": "re-register endpoints under v3 and verify with verify()",
    "migration_signals": ["re-register", "verify()", "not accepted by v3", "v3 signature"],
    "source": "data/documents/v2/migrating-to-v3.md ('Re-register webhook endpoints; v2 signatures are not accepted by v3')"
  }
]
```

- [ ] **Step 7: Generate symbols.json**

Run: `venv/bin/python -m eval.spec.build_symbols`
Expected: `wrote .../eval/spec/symbols.json with <N> symbols` where N is roughly 40–60.

- [ ] **Step 8: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_spec_artifacts.py -v`
Expected: all 8 PASS.

If `test_extract_symbols_excludes_python_builtins_and_bare_words` fails, add
the offending token to `STOPLIST` in `build_symbols.py` and regenerate — do
not weaken the test, because that token appearing in the table is exactly what
would make A2 fail on ordinary prose.

- [ ] **Step 9: Commit**

```bash
git add eval/spec tests/test_week6_spec_artifacts.py
git commit -m "week6: spec artifacts (symbols, openapi, deprecations) for deterministic assertions"
```

---

### Task 2: Assertion framework, A1 (code parses) and A4 (version stated)

**Files:**
- Create: `eval/week6/__init__.py`
- Create: `eval/week6/assertions.py`
- Test: `tests/test_week6_assertions.py`

**Interfaces:**
- Consumes: nothing from Task 1 yet (A1 and A4 need no spec artifact)
- Produces:
  - Constants `PASS = "pass"`, `FAIL = "fail"`, `SKIPPED = "skipped"`
  - `assert_code_parses(answer: str) -> dict`
  - `assert_version_stated(answer: str, version_sensitive: bool) -> dict`
  - Every assertion returns `{"id": str, "status": str, "detail": str}`
  - `strip_code_fences(answer: str) -> str` — prose with fenced blocks removed, used by Task 3

- [ ] **Step 1: Write the failing test**

Create `tests/test_week6_assertions.py`:

```python
"""The five deterministic assertions moved out of judge_v0.

Each one gets a passing case, a failing case, and a not-applicable case. The
not-applicable cases matter as much as the others: an assertion that returns
"pass" when it did not actually run would let A3 alone donate ~20 free passes
to the 25-case table and manufacture a pass rate out of nothing.
"""
from eval.week6.assertions import (
    FAIL,
    PASS,
    SKIPPED,
    assert_code_parses,
    assert_version_stated,
)


def test_a1_passes_a_valid_python_fence():
    answer = "Use this:\n\n```python\nclient.send(message='x', channel='a/b/c')\n```\n"
    assert assert_code_parses(answer)["status"] == PASS


def test_a1_fails_a_fence_that_does_not_parse():
    answer = "```python\nclient.send(message='x',\n```\n"
    result = assert_code_parses(answer)
    assert result["status"] == FAIL
    assert "fence 0" in result["detail"]


def test_a1_is_skipped_when_the_answer_has_no_python_fence():
    result = assert_code_parses("The default is 2000 ms. [chunk: v3:client:structural:2]")
    assert result["status"] == SKIPPED, "no fence is not the same as a valid fence"


def test_a1_checks_every_fence_not_just_the_first():
    answer = "```python\nx = 1\n```\n\ntext\n\n```python\ndef broken(\n```\n"
    assert assert_code_parses(answer)["status"] == FAIL


def test_a1_tolerates_an_indented_fence():
    answer = "```python\n    receipt = client.send(message='x')\n```\n"
    assert assert_code_parses(answer)["status"] == PASS


def test_a4_passes_when_the_answer_names_a_version():
    result = assert_version_stated("In v3 the default is 2000 ms.", True)
    assert result["status"] == PASS
    assert "v3" in result["detail"]


def test_a4_fails_when_a_version_sensitive_answer_names_no_version():
    result = assert_version_stated("The default retry backoff is 2000 ms.", True)
    assert result["status"] == FAIL


def test_a4_is_skipped_for_a_case_that_is_not_version_sensitive():
    assert assert_version_stated("Anything.", False)["status"] == SKIPPED


def test_a4_does_not_judge_whether_the_version_is_correct():
    """Stated-ness is deterministic; correctness is the judge's half. An answer
    that confidently names the WRONG version still passes A4 -- that split is
    the whole point of the assertion/judge seam."""
    assert assert_version_stated("In v2 the default is 2000 ms.", True)["status"] == PASS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_assertions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.week6'`

- [ ] **Step 3: Write the implementation**

Create `eval/week6/__init__.py` (empty file), then `eval/week6/assertions.py`:

```python
"""The five deterministic criteria moved out of the LLM judge.

judge_v0 asked a model six questions about every answer. Five of them were
facts a program can settle exactly -- does this code parse, does this symbol
exist, is a version named, is a deprecated thing recommended without a
migration note -- and one was a judgement. Paying a model to answer the five
is slower, costlier, and less reliable than a parser and three lookups, so
they live here and were deleted from the prompt.

Every assertion returns one of three statuses. "skipped" means the assertion
did not apply to this answer and is NOT counted as a pass anywhere.
"""
import ast
import re
import textwrap

PASS = "pass"
FAIL = "fail"
SKIPPED = "skipped"

A1 = "A1_code_parses"
A2 = "A2_symbols_exist"
A3 = "A3_endpoints_exist"
A4 = "A4_version_stated"
A5 = "A5_deprecation_has_migration_note"

ASSERTION_IDS = (A1, A2, A3, A4, A5)

_PY_FENCE_RE = re.compile(r"```(?:python|py)[^\n]*\n(.*?)```", re.DOTALL)
_ANY_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_VERSION_RE = re.compile(r"\bv[23]\b")


def _result(assertion_id: str, status: str, detail: str) -> dict:
    return {"id": assertion_id, "status": status, "detail": detail}


def strip_code_fences(answer: str) -> str:
    """Answer prose with fenced code blocks removed.

    A2 scans prose only. Local variable names a code sample invents
    (`my_client`, `raw_payload`) are not SDK symbols, and checking them
    against the symbol table would fail on perfectly good examples.
    """
    return _ANY_FENCE_RE.sub("\n", answer)


def assert_code_parses(answer: str) -> dict:
    """A1: every python fence in the answer survives ast.parse."""
    fences = _PY_FENCE_RE.findall(answer)
    if not fences:
        return _result(A1, SKIPPED, "answer contains no python fence")

    offenders = []
    for index, code in enumerate(fences):
        try:
            ast.parse(textwrap.dedent(code))
        except SyntaxError as exc:
            offenders.append(f"fence {index}: {exc.msg} (line {exc.lineno})")

    if offenders:
        return _result(A1, FAIL, "; ".join(offenders))
    return _result(A1, PASS, f"{len(fences)} python fence(s) parsed")


def assert_version_stated(answer: str, version_sensitive: bool) -> dict:
    """A4: a version-sensitive answer must name v2 or v3 explicitly.

    Checks stated-ness only. Whether the named version is the RIGHT one is a
    judgement and stays with the judge -- that is the seam between the
    deterministic half and the judged half.
    """
    if not version_sensitive:
        return _result(A4, SKIPPED, "case is not version-sensitive")

    found = sorted(set(_VERSION_RE.findall(answer)))
    if found:
        return _result(A4, PASS, f"states {', '.join(found)}")
    return _result(A4, FAIL, "no v2/v3 named anywhere in the answer")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_assertions.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add eval/week6/__init__.py eval/week6/assertions.py tests/test_week6_assertions.py
git commit -m "week6: assertion framework with A1 code-parses and A4 version-stated"
```

---

### Task 3: A2 (symbols exist), A3 (endpoints exist), A5 (deprecation note)

**Files:**
- Modify: `eval/week6/assertions.py`
- Modify: `tests/test_week6_assertions.py`

**Interfaces:**
- Consumes: `eval.spec.load_specs()` from Task 1; `PASS`/`FAIL`/`SKIPPED`, `strip_code_fences` from Task 2
- Produces:
  - `assert_symbols_exist(answer: str, symbols: dict) -> dict`
  - `assert_endpoints_exist(answer: str, openapi: dict) -> dict`
  - `assert_deprecation_has_migration_note(answer: str, deprecations: list[dict]) -> dict`
  - `run_assertions(answer: str, case: dict, specs: dict) -> list[dict]` — all five, in `ASSERTION_IDS` order
  - `assertions_ok(results: list[dict]) -> bool` — True when no result has status `FAIL`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_week6_assertions.py`:

```python
from eval.week6.assertions import (
    assert_deprecation_has_migration_note,
    assert_endpoints_exist,
    assert_symbols_exist,
    assertions_ok,
    run_assertions,
)

SYMBOLS = {
    "RELAY_429": {"kind": "error_code", "versions": ["v2", "v3"], "sources": []},
    "retry_backoff_ms": {"kind": "parameter", "versions": ["v2", "v3"], "sources": []},
    "Client.send()": {"kind": "method", "versions": ["v2", "v3"], "sources": []},
    "RelayTimeout": {"kind": "class", "versions": ["v3"], "sources": []},
}

OPENAPI = {"paths": {"/v3/auth/token": {"post": {}}}}

DEPRECATIONS = [
    {
        "id": "offset-pagination",
        "label": "offset pagination",
        "match": r"\b(page_offset|offset pagination)\b",
        "replacement": "next_cursor",
        "migration_signals": ["next_cursor", "removed in v3"],
        "source": "migrating-to-v3.md",
    }
]


def test_a2_passes_an_answer_using_only_real_symbols():
    answer = "`Client.send()` retries on `RELAY_429`; tune `retry_backoff_ms`."
    assert assert_symbols_exist(answer, SYMBOLS)["status"] == PASS


def test_a2_fails_a_fabricated_error_code():
    result = assert_symbols_exist("Handle `RELAY_777` on failure.", SYMBOLS)
    assert result["status"] == FAIL
    assert "RELAY_777" in result["detail"]


def test_a2_fails_a_fabricated_parameter():
    result = assert_symbols_exist("Set `retry_delay_ms` to 2000.", SYMBOLS)
    assert result["status"] == FAIL
    assert "retry_delay_ms" in result["detail"]


def test_a2_fails_a_fabricated_qualified_method():
    result = assert_symbols_exist("Call `Client.sendBatch()` instead.", SYMBOLS)
    assert result["status"] == FAIL


def test_a2_never_examines_bare_prose_words_or_builtins():
    """The corpus backticks `str`, `int`, `None`, `message`. Checking those
    against the table would fail on ordinary English, so the shape rules
    exclude every single-word token.

    A real symbol is included so this asserts PASS rather than SKIPPED --
    otherwise the test would pass simply because nothing was examined, and
    would keep passing if the noise-filtering broke.
    """
    answer = "`RELAY_429` is retried; the `message` is a `str`, `metadata` is `None`, `id` an `int`."
    assert assert_symbols_exist(answer, SYMBOLS)["status"] == PASS


def test_a2_ignores_local_variables_inside_code_fences():
    answer = "```python\nmy_client = Client(api_key='k')\nraw_payload = {}\n```\n"
    assert assert_symbols_exist(answer, SYMBOLS)["status"] == SKIPPED


def test_a2_is_skipped_when_no_sdk_shaped_token_appears():
    assert assert_symbols_exist("The docs do not say.", SYMBOLS)["status"] == SKIPPED


def test_a3_passes_the_one_documented_path():
    answer = "Exchange the key at `POST /v3/auth/token`."
    assert assert_endpoints_exist(answer, OPENAPI)["status"] == PASS


def test_a3_fails_a_hallucinated_endpoint():
    result = assert_endpoints_exist("Refresh via `POST /v3/tokens/refresh`.", OPENAPI)
    assert result["status"] == FAIL
    assert "/v3/tokens/refresh" in result["detail"]


def test_a3_is_skipped_when_the_answer_mentions_no_path():
    assert assert_endpoints_exist("The SDK handles it.", OPENAPI)["status"] == SKIPPED


def test_a3_strips_trailing_punctuation_from_a_path():
    assert assert_endpoints_exist("Call /v3/auth/token.", OPENAPI)["status"] == PASS


def test_a5_passes_a_deprecated_mention_that_carries_its_migration_note():
    answer = "v2 used offset pagination; in v3 thread `next_cursor` instead."
    assert assert_deprecation_has_migration_note(answer, DEPRECATIONS)["status"] == PASS


def test_a5_fails_a_deprecated_recommendation_with_no_note():
    answer = "Use offset pagination to page through results."
    result = assert_deprecation_has_migration_note(answer, DEPRECATIONS)
    assert result["status"] == FAIL
    assert "offset-pagination" in result["detail"]


def test_a5_requires_the_note_in_the_same_paragraph():
    """A migration note three paragraphs away does not help a reader who
    copies the code block next to the deprecated mention."""
    answer = "Use offset pagination to page.\n\nUnrelated.\n\nv3 uses `next_cursor`."
    assert assert_deprecation_has_migration_note(answer, DEPRECATIONS)["status"] == FAIL


def test_a5_falls_back_to_a_character_window_with_no_blank_lines():
    answer = "Use offset pagination, though v3 replaced it with next_cursor."
    assert assert_deprecation_has_migration_note(answer, DEPRECATIONS)["status"] == PASS


def test_a5_is_skipped_when_no_deprecated_thing_is_mentioned():
    answer = "The default retry backoff is 2000 ms in v3."
    assert assert_deprecation_has_migration_note(answer, DEPRECATIONS)["status"] == SKIPPED


def test_run_assertions_returns_all_five_in_order():
    case = {"version_sensitive": True}
    specs = {"symbols": SYMBOLS, "openapi": OPENAPI, "deprecations": DEPRECATIONS}
    results = run_assertions("In v3 the default is 2000 ms.", case, specs)
    assert [r["id"] for r in results] == list(ASSERTION_IDS)


def test_assertions_ok_treats_skipped_as_not_a_failure():
    results = [{"id": A1, "status": SKIPPED, "detail": ""}, {"id": A4, "status": PASS, "detail": ""}]
    assert assertions_ok(results) is True


def test_assertions_ok_is_false_when_anything_failed():
    results = [{"id": A1, "status": PASS, "detail": ""}, {"id": A4, "status": FAIL, "detail": ""}]
    assert assertions_ok(results) is False
```

Add `ASSERTION_IDS`, `A1` and `A4` to the existing import block at the top of the test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_assertions.py -v`
Expected: FAIL — `ImportError: cannot import name 'assert_symbols_exist'`

- [ ] **Step 3: Write the implementation**

Append to `eval/week6/assertions.py`:

```python
# A2 selects tokens to check by SHAPE, then passes or fails them on presence
# in the symbol table. Selecting by presence instead would be circular --
# nothing could ever fail. The required underscore in _PARAM_RE is what keeps
# single prose words (`str`, `message`, `id`) out without a stoplist.
_ERROR_CODE_RE = re.compile(r"\b(?:RELAY_\d{3}|AUTH_[A-Z_]{3,})\b")
_CLASS_RE = re.compile(r"\b(?:Relay[A-Z]\w*|Signature[A-Z]\w*|Stream[A-Z]\w*|[A-Z]\w*Cache)\b")
_METHOD_RE = re.compile(r"\bClient\.\w+\(\)")
# Parameters are read only from inline-code spans. Bare snake_case in prose is
# too often an English phrase, and inside a fence it is usually a local
# variable the example invented.
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_PARAM_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
_PATH_RE = re.compile(r"(?:(?:GET|POST|PUT|PATCH|DELETE)\s+)?(/v\d+/[A-Za-z0-9/_{}.-]+)")


def _candidate_symbols(answer: str) -> list[str]:
    prose = strip_code_fences(answer)
    found: list[str] = []
    found.extend(_ERROR_CODE_RE.findall(prose))
    found.extend(_CLASS_RE.findall(prose))
    found.extend(_METHOD_RE.findall(prose))
    for span in _INLINE_CODE_RE.findall(prose):
        token = span.strip()
        if _PARAM_RE.match(token):
            found.append(token)
    return list(dict.fromkeys(found))


def assert_symbols_exist(answer: str, symbols: dict) -> dict:
    """A2: every SDK-shaped token in the answer exists in the symbol table."""
    candidates = _candidate_symbols(answer)
    if not candidates:
        return _result(A2, SKIPPED, "answer names no SDK-shaped symbol")

    unknown = [name for name in candidates if name not in symbols]
    if unknown:
        return _result(A2, FAIL, f"not in the SDK: {', '.join(unknown)}")
    return _result(A2, PASS, f"{len(candidates)} symbol(s) resolved")


def assert_endpoints_exist(answer: str, openapi: dict) -> dict:
    """A3: every /vN/... path mentioned appears in the OpenAPI spec.

    Applies to only a handful of cases, because the whole corpus documents one
    endpoint path. Kept anyway: "how do I authenticate in v3?" is exactly
    where a model invents /v3/tokens/refresh, and a guard that fires rarely
    but catches fabrication is still worth having. The applicable count is
    reported so the small N stays visible rather than hidden.
    """
    known = set(openapi.get("paths", {}))
    found = [m.group(1).rstrip(".,;:)`") for m in _PATH_RE.finditer(strip_code_fences(answer))]
    found = list(dict.fromkeys(found))
    if not found:
        return _result(A3, SKIPPED, "answer mentions no endpoint path")

    unknown = [path for path in found if path not in known]
    if unknown:
        return _result(A3, FAIL, f"not in the spec: {', '.join(unknown)}")
    return _result(A3, PASS, f"{len(found)} path(s) found in the spec")


def _paragraph_around(text: str, start: int, end: int) -> str:
    """The blank-line-delimited block containing a match.

    Falls back to a +/-300 character window when the answer has no blank
    lines. The window size is fixed here rather than tuned later because it
    is the difference between a strict and a lenient assertion, and that
    should not be an accident.
    """
    if "\n\n" not in text:
        return text[max(0, start - 300) : end + 300]
    left = text.rfind("\n\n", 0, start)
    left = 0 if left == -1 else left + 2
    right = text.find("\n\n", end)
    right = len(text) if right == -1 else right
    return text[left:right]


def assert_deprecation_has_migration_note(answer: str, deprecations: list[dict]) -> dict:
    """A5: a deprecated thing never appears without a migration signal nearby."""
    offenders = []
    matched_any = False

    for entry in deprecations:
        match = re.search(entry["match"], answer, re.IGNORECASE)
        if match is None:
            continue
        matched_any = True
        window = _paragraph_around(answer, match.start(), match.end()).lower()
        if not any(signal.lower() in window for signal in entry["migration_signals"]):
            offenders.append(entry["id"])

    if not matched_any:
        return _result(A5, SKIPPED, "answer mentions nothing on the deprecations list")
    if offenders:
        return _result(A5, FAIL, f"no migration note beside: {', '.join(offenders)}")
    return _result(A5, PASS, "every deprecated mention carries a migration note")


def run_assertions(answer: str, case: dict, specs: dict) -> list[dict]:
    """All five assertions, always in ASSERTION_IDS order."""
    return [
        assert_code_parses(answer),
        assert_symbols_exist(answer, specs["symbols"]),
        assert_endpoints_exist(answer, specs["openapi"]),
        assert_version_stated(answer, case.get("version_sensitive", False)),
        assert_deprecation_has_migration_note(answer, specs["deprecations"]),
    ]


def assertions_ok(results: list[dict]) -> bool:
    """True when nothing failed. A skipped assertion is not a pass, but it is
    also not a failure -- it simply did not apply."""
    return all(r["status"] != FAIL for r in results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_assertions.py -v`
Expected: 27 PASS.

- [ ] **Step 5: Verify the assertions against the real spec artifacts**

Run:

```bash
venv/bin/python -c "
from eval.spec import load_specs
from eval.week6.assertions import run_assertions
specs = load_specs()
answer = 'In v3 the default \`retry_backoff_ms\` is 2000 ms and \`Client.send()\` retries on \`RELAY_429\`.'
for r in run_assertions(answer, {'version_sensitive': True}, specs):
    print(r['id'], r['status'], '-', r['detail'])
"
```

Expected: A1 skipped, A2 pass, A3 skipped, A4 pass, A5 skipped. If A2 fails,
a real symbol is missing from `symbols.json` — fix the extractor's patterns in
Task 1 and regenerate rather than loosening A2.

- [ ] **Step 6: Commit**

```bash
git add eval/week6/assertions.py tests/test_week6_assertions.py
git commit -m "week6: assertions A2 symbols, A3 endpoints, A5 deprecation-migration-note"
```

---

### Task 4: The 25 mode-tagged cases

**Files:**
- Create: `eval/week6/build_cases.py`
- Create: `eval/week6/cases.jsonl`
- Test: `tests/test_week6_cases.py`

**Interfaces:**
- Consumes: `rag.tracing.load_traces()`
- Produces:
  - `eval.week6.build_cases.MODES` — tuple of the five mode strings
  - `eval.week6.build_cases.load_cases(path: Path | None = None) -> list[dict]`
  - `eval.week6.build_cases.case_from_trace(trace: dict, case_id: str, mode: str, version_sensitive: bool, notes: str) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_week6_cases.py`:

```python
"""Integrity of the 25-case eval set.

The mode tags are the Week 5 taxonomy names verbatim, so the two write-ups
line up. Regression cases are lifted out of traces.jsonl by script rather
than retyped, which is what makes "replayed verbatim" checkable instead of a
claim.
"""
from eval.week6.build_cases import MODES, case_from_trace, load_cases
from rag.tracing import load_traces

TRACE = {
    "trace_id": "b84fe53eb006",
    "question": "What's the default retry backoff for Client.send()?",
    "strategy": "structural",
    "k": 4,
    "where": None,
    "rerank": False,
    "model": "openai/gpt-oss-120b",
    "model_params": {"max_tokens": 2048},
    "retrieved": [
        {
            "chunk_id": "v2:client:structural:3",
            "dense_distance": 0.5132670402526855,
            "bm25_score": 19.004,
            "rrf_score": 0.0327,
            "rerank_score": None,
        }
    ],
}


def test_case_from_trace_copies_every_execution_parameter():
    case = case_from_trace(TRACE, "W6-07", "version-ambiguity", True, "note")
    assert case["question"] == TRACE["question"]
    assert case["retrieval"] == {"k": 4, "where": None, "strategy": "structural", "rerank": False}
    assert case["generation"] == {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}
    assert case["origin"] == {"kind": "replay", "trace_id": "b84fe53eb006"}


def test_case_from_trace_carries_the_logged_retrieval_scores():
    """Not just the chunk ids. should_refuse() treats a chunk with no
    dense_distance as no evidence, so a case that kept only the ids would
    answer with the refusal string instead of reproducing its failure -- which
    would quietly void every regression case in the set."""
    case = case_from_trace(TRACE, "W6-07", "version-ambiguity", True, "note")
    assert case["replay_retrieved"][0]["chunk_id"] == "v2:client:structural:3"
    assert case["replay_retrieved"][0]["dense_distance"] == 0.5132670402526855
    assert case["replay_retrieved"][0]["bm25_score"] == 19.004


def test_every_replay_case_has_at_least_one_scored_chunk():
    for case in load_cases():
        if case["origin"]["kind"] != "replay":
            continue
        scored = [
            r for r in case["replay_retrieved"] if r["dense_distance"] is not None
        ]
        assert scored, f"{case['case_id']} would refuse for lack of dense scores"


def test_there_are_at_least_25_cases():
    assert len(load_cases()) >= 25


def test_every_case_has_exactly_one_known_mode():
    for case in load_cases():
        assert case["mode"] in MODES, case["case_id"]


def test_every_mode_is_represented():
    used = {case["mode"] for case in load_cases()}
    assert used == set(MODES)


def test_case_ids_are_unique():
    ids = [case["case_id"] for case in load_cases()]
    assert len(ids) == len(set(ids))


def test_at_least_two_cases_are_real_replayed_regressions():
    replays = [c for c in load_cases() if c["origin"]["kind"] == "replay"]
    assert len(replays) >= 2


def test_every_replay_case_matches_its_trace_verbatim():
    """This is what "replayed verbatim" means: not a paraphrase of a failure
    we remember, but the exact question and parameters that were logged."""
    traces = {t["trace_id"]: t for t in load_traces()}
    for case in load_cases():
        if case["origin"]["kind"] != "replay":
            continue
        trace = traces[case["origin"]["trace_id"]]
        assert case["question"] == trace["question"], case["case_id"]
        assert case["retrieval"]["k"] == trace["k"], case["case_id"]
        assert case["retrieval"]["where"] == trace["where"], case["case_id"]
        assert case["retrieval"]["strategy"] == trace["strategy"], case["case_id"]
        assert case["retrieval"]["rerank"] == trace["rerank"], case["case_id"]
        assert case["generation"]["model"] == trace["model"], case["case_id"]


def test_authored_cases_declare_what_they_were_based_on():
    for case in load_cases():
        if case["origin"]["kind"] == "authored":
            assert case["origin"]["basis"], case["case_id"]


def test_version_ambiguity_cases_are_all_version_sensitive():
    """sdk_version_intent "unspecified" does not mean the version does not
    matter -- it is the bucket where stating it matters most."""
    for case in load_cases():
        if case["mode"] == "version-ambiguity":
            assert case["version_sensitive"] is True, case["case_id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_cases.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.week6.build_cases'`

- [ ] **Step 3: Write the case builder**

Create `eval/week6/build_cases.py`:

```python
"""The 25-case eval set: five cases per Week 5 failure mode.

Regression cases are lifted from eval/traces.jsonl by --from-trace rather than
retyped. A hand-retyped question is a paraphrase of a failure someone
remembers; a lifted one is the failure that actually happened, with the same
k, where, strategy, rerank, model and params it happened under.
"""
import argparse
import json
from pathlib import Path

from rag.tracing import load_traces

BASE = Path(__file__).resolve().parent
CASES_PATH = BASE / "cases.jsonl"

# Verbatim from results/week5/taxonomy.md, plus "clean" for the cases expected
# to pass. Renaming any of these would break the link between the two weeks.
MODES = (
    "citation-format",
    "version-ambiguity",
    "cross-product-bleed",
    "unexplained-refusal",
    "clean",
)


def case_from_trace(
    trace: dict, case_id: str, mode: str, version_sensitive: bool, notes: str
) -> dict:
    return {
        "case_id": case_id,
        "question": trace["question"],
        "mode": mode,
        "origin": {"kind": "replay", "trace_id": trace["trace_id"]},
        "version_sensitive": version_sensitive,
        "sdk_version_intent": "unspecified",
        "retrieval": {
            "k": trace["k"],
            "where": trace["where"],
            "strategy": trace["strategy"],
            "rerank": trace["rerank"],
        },
        "generation": {"model": trace["model"], "model_params": trace["model_params"]},
        # The full logged records, not just the ids. rag.generator.should_refuse
        # treats a chunk with no dense_distance as no evidence and refuses, so
        # dropping the scores here would make every replay case answer with the
        # refusal string instead of reproducing its failure. eval/replay.py does
        # the same thing for the same reason.
        "replay_retrieved": [
            {
                "chunk_id": r["chunk_id"],
                "dense_distance": r["dense_distance"],
                "bm25_score": r["bm25_score"],
                "rrf_score": r["rrf_score"],
                "rerank_score": r.get("rerank_score"),
            }
            for r in trace["retrieved"]
        ],
        "notes": notes,
    }


def load_cases(path: Path | None = None) -> list[dict]:
    path = path or CASES_PATH
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-trace", required=True, help="trace_id to lift a case from")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--version-sensitive", action="store_true")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    trace = next(t for t in load_traces() if t["trace_id"] == args.from_trace)
    case = case_from_trace(
        trace, args.case_id, args.mode, args.version_sensitive, args.notes
    )
    print(json.dumps(case, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Generate the four regression cases**

Run each of these and append the output line to `eval/week6/cases.jsonl`:

```bash
cd /Users/balamurugan/Documents/Projects/pythom/AiLearning
: > eval/week6/cases.jsonl
venv/bin/python -m eval.week6.build_cases --from-trace 15f8e03f9de3 --case-id W6-01 \
  --mode citation-format --version-sensitive \
  --notes "Week 5 example trace for full-width-bracket citations." >> eval/week6/cases.jsonl
venv/bin/python -m eval.week6.build_cases --from-trace b84fe53eb006 --case-id W6-06 \
  --mode version-ambiguity --version-sensitive \
  --notes "Week 5 example trace: one version's numbers while the other version's chunk was retrieved." >> eval/week6/cases.jsonl
venv/bin/python -m eval.week6.build_cases --from-trace e7443d69a8a9 --case-id W6-11 \
  --mode cross-product-bleed --version-sensitive \
  --notes "Week 5 example trace: answered from the unrelated second product in the index." >> eval/week6/cases.jsonl
venv/bin/python -m eval.week6.build_cases --from-trace 132709d13774 --case-id W6-16 \
  --mode unexplained-refusal --version-sensitive \
  --notes "Week 5 example trace: refused despite four on-target chunks." >> eval/week6/cases.jsonl
wc -l eval/week6/cases.jsonl
```

Expected: 4 lines.

- [ ] **Step 5: Append the remaining 21 cases**

Append these 21 lines verbatim to `eval/week6/cases.jsonl`. Four more per mode
for the first four modes, five for `clean` — bringing every mode to five and
the file to 25.

Each question was chosen so the mode is actually exercised: the
`version-ambiguity` questions name no version *and* have genuinely different
answers in v2 and v3; the `cross-product-bleed` questions say "the SDK"
generically while the index also holds `OMNUMI_SDK_IOS_DOCUMENTATION.md` and
two PDFs; the `unexplained-refusal` questions are answerable from
`data/documents/v3` but use none of the wording their source section uses.

```bash
cat >> eval/week6/cases.jsonl <<'CASES'
{"case_id": "W6-02", "question": "What's the maximum accepted value for dedupe_window_ms on Client.send()?", "mode": "citation-format", "origin": {"kind": "authored", "basis": "golden_set:Q2"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Parameter-limit lookup; the mode under test is citation shape, not the value."}
{"case_id": "W6-03", "question": "Which error code means the bearer token is past its expiry?", "mode": "citation-format", "origin": {"kind": "authored", "basis": "golden_set:Q3"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Single error-code lookup that must be cited to one chunk."}
{"case_id": "W6-04", "question": "What hashing algorithm does Relay use to sign webhook requests?", "mode": "citation-format", "origin": {"kind": "authored", "basis": "golden_set:Q7"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "One-fact prose answer; a citation is the only thing that can go wrong."}
{"case_id": "W6-05", "question": "What's the maximum page_size I can request from Client.fetch()?", "mode": "citation-format", "origin": {"kind": "authored", "basis": "golden_set:Q12"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Parameter-table limit; v3-only page, so no version confusion is available."}
{"case_id": "W6-07", "question": "What format does a channel identifier take?", "mode": "version-ambiguity", "origin": {"kind": "authored", "basis": "v2/migrating-to-v3.md (org/topic -> org/team/topic)"}, "version_sensitive": true, "sdk_version_intent": "unspecified", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "v2 takes org/topic, v3 rejects it with RELAY_400. Version left unstated on purpose."}
{"case_id": "W6-08", "question": "How do I page through a long list of results?", "mode": "version-ambiguity", "origin": {"kind": "authored", "basis": "v2/migrating-to-v3.md (offset removed in favour of cursors)"}, "version_sensitive": true, "sdk_version_intent": "unspecified", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "v2 used offsets, v3 removed them entirely for cursors."}
{"case_id": "W6-09", "question": "How does authentication work in the Relay SDK?", "mode": "version-ambiguity", "origin": {"kind": "authored", "basis": "v2/auth.md vs v3/auth.md"}, "version_sensitive": true, "sdk_version_intent": "unspecified", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "v2 sends a long-lived key per request; v3 exchanges it for a short-lived token."}
{"case_id": "W6-10", "question": "How many delivery attempts does a failed send get by default?", "mode": "version-ambiguity", "origin": {"kind": "authored", "basis": "v3/client.md retry_max_attempts vs v2/CHANGELOG.md 2.5.0"}, "version_sensitive": true, "sdk_version_intent": "unspecified", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "v3 defaults to 4 attempts with exponential backoff; v2 was fixed at 3, 500 ms apart."}
{"case_id": "W6-12", "question": "How should I handle errors in the SDK?", "mode": "cross-product-bleed", "origin": {"kind": "authored", "basis": "generic phrasing over a multi-product index"}, "version_sensitive": true, "sdk_version_intent": "unspecified", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "The index also holds OMNUMI_SDK_IOS_DOCUMENTATION.md and two PDFs."}
{"case_id": "W6-13", "question": "How do I initialise a client in the SDK?", "mode": "cross-product-bleed", "origin": {"kind": "authored", "basis": "generic phrasing over a multi-product index"}, "version_sensitive": true, "sdk_version_intent": "unspecified", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Both products document a client constructor, so the question is genuinely ambiguous."}
{"case_id": "W6-14", "question": "What is the default timeout in the SDK?", "mode": "cross-product-bleed", "origin": {"kind": "authored", "basis": "generic phrasing over a multi-product index"}, "version_sensitive": true, "sdk_version_intent": "unspecified", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "timeout_ms is a Relay parameter; the other product has its own unrelated default."}
{"case_id": "W6-15", "question": "How does the SDK retry failed requests?", "mode": "cross-product-bleed", "origin": {"kind": "authored", "basis": "generic phrasing over a multi-product index"}, "version_sensitive": true, "sdk_version_intent": "unspecified", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Retry semantics differ between the two products AND between Relay v2 and v3."}
{"case_id": "W6-17", "question": "What happens if a subscriber cannot keep up with incoming messages?", "mode": "unexplained-refusal", "origin": {"kind": "authored", "basis": "v3/streaming.md (Backpressure)"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Answerable from the Backpressure section, but the question uses none of its wording."}
{"case_id": "W6-18", "question": "If a paginated listing runs for a long time, can the cursor stop working?", "mode": "unexplained-refusal", "origin": {"kind": "authored", "basis": "v3/pagination.md (Cursor stability)"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Answerable from Cursor stability; phrased as a scenario rather than a term."}
{"case_id": "W6-19", "question": "How does the client behave when a stream connection drops mid-subscription?", "mode": "unexplained-refusal", "origin": {"kind": "authored", "basis": "v3/streaming.md (Reconnection)"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Answerable from Reconnection; the word 'reconnection' never appears in the question."}
{"case_id": "W6-20", "question": "How do I restrict what a token is allowed to do?", "mode": "unexplained-refusal", "origin": {"kind": "authored", "basis": "v3/auth.md (Scopes)"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Answerable from Scopes; asks for the capability rather than naming it."}
{"case_id": "W6-21", "question": "What is the default value of retry_backoff_ms for Client.send() in the v3 SDK?", "mode": "clean", "origin": {"kind": "authored", "basis": "golden_set:Q1"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Version named in the question; single-chunk answer."}
{"case_id": "W6-22", "question": "How long is a v3 access token valid before it needs to be refreshed?", "mode": "clean", "origin": {"kind": "authored", "basis": "golden_set:Q8"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Version named; one number on one page."}
{"case_id": "W6-23", "question": "What argument do I pass to Client.subscribe() to get messages as they arrive instead of a buffered list?", "mode": "clean", "origin": {"kind": "authored", "basis": "golden_set:Q9"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "v3-only page, unambiguous parameter."}
{"case_id": "W6-24", "question": "Is it safe to call Client.close() twice in the v3 SDK?", "mode": "clean", "origin": {"kind": "authored", "basis": "golden_set:Q11"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "Version named; a yes/no with a stated reason."}
{"case_id": "W6-25", "question": "How many delivery attempts will Relay make for a webhook before marking it exhausted?", "mode": "clean", "origin": {"kind": "authored", "basis": "golden_set:Q10"}, "version_sensitive": true, "sdk_version_intent": "v3", "retrieval": {"k": 4, "where": null, "strategy": "structural", "rerank": false}, "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}, "replay_retrieved": null, "notes": "v3-only webhooks page; one number."}
CASES
wc -l eval/week6/cases.jsonl
```

Expected: 25 lines.

- [ ] **Step 6: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_cases.py -v`
Expected: 9 PASS. If `test_every_replay_case_matches_its_trace_verbatim` fails,
a case was hand-edited after generation — regenerate it with `--from-trace`
instead of fixing the JSON by hand.

- [ ] **Step 7: Commit**

```bash
git add eval/week6/build_cases.py eval/week6/cases.jsonl tests/test_week6_cases.py
git commit -m "week6: 25 mode-tagged eval cases incl. 4 verbatim trace replays"
```

---

### Task 5: Judge prompts v0 and v1, and the shared criterion

**Files:**
- Create: `results/week6/judge_v0.txt`
- Create: `results/week6/judge_v1.txt`
- Create: `eval/week6/criterion.py`
- Test: `tests/test_week6_judge_prompts.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `eval.week6.criterion.CRITERION_MARKER = "CRITERION:"`
  - `eval.week6.criterion.read_criterion(path: Path) -> str`
  - `eval.week6.criterion.sha256_text(text: str) -> str`
  - `eval.week6.criterion.JUDGE_V1_PATH`, `JUDGE_V0_PATH`, `JUDGE_V2_PATH` as `Path`

- [ ] **Step 1: Write the failing test**

Create `tests/test_week6_judge_prompts.py`:

```python
"""judge_v0 -> judge_v1 is the assertion/judge split, as a diff.

v0 asks six questions, five of which a program can settle exactly. v1 is v0
with those five deleted. The test asserts the deletion actually happened,
because a "split" that leaves the criteria in the prompt is cosmetic -- the
judge would go on silently re-litigating what the assertions already decided.
"""
from eval.week6.criterion import (
    JUDGE_V0_PATH,
    JUDGE_V1_PATH,
    read_criterion,
    sha256_text,
)

# Wording that would show a moved criterion is still being judged.
ASSERTED_CRITERIA_MARKERS = [
    "syntactically valid",
    "exists in the SDK",
    "exists in the API spec",
    "states which SDK version",
    "without a migration note",
]


def test_v0_contains_all_six_criteria():
    text = JUDGE_V0_PATH.read_text(encoding="utf-8")
    for marker in ASSERTED_CRITERIA_MARKERS:
        assert marker in text, f"v0 should still ask about: {marker}"


def test_v1_has_deleted_every_asserted_criterion():
    text = JUDGE_V1_PATH.read_text(encoding="utf-8").lower()
    for marker in ASSERTED_CRITERIA_MARKERS:
        assert marker.lower() not in text, f"v1 still judges an asserted criterion: {marker}"


def test_v1_tells_the_judge_not_to_re_judge_the_asserted_things():
    text = JUDGE_V1_PATH.read_text(encoding="utf-8").lower()
    assert "checked separately" in text or "checked deterministically" in text


def test_v1_declares_exactly_one_criterion():
    text = JUDGE_V1_PATH.read_text(encoding="utf-8")
    assert text.count("CRITERION:") == 1


def test_v1_demands_the_strict_output_contract():
    text = JUDGE_V1_PATH.read_text(encoding="utf-8")
    assert "VERDICT:" in text and "REASON:" in text
    assert "1-10" not in text and "1 to 10" not in text, "must be binary, not a scale"


def test_read_criterion_returns_the_single_criterion_line():
    criterion = read_criterion(JUDGE_V1_PATH)
    assert criterion.startswith("Would a developer")
    assert "CRITERION:" not in criterion


def test_sha256_text_is_stable():
    assert sha256_text("abc") == sha256_text("abc")
    assert sha256_text("abc") != sha256_text("abd")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_judge_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.week6.criterion'`

- [ ] **Step 3: Write judge_v0.txt**

Create `results/week6/judge_v0.txt`. This is the naive judge deliberately
written *before* the split, so requirement 2's deletion is a real diff:

```
You are grading an answer produced by a documentation assistant for the Relay SDK.

You will be shown the user's question, the documentation excerpts the assistant
retrieved, and the answer it produced.

Grade the answer against all six criteria below. If it satisfies every one,
reply PASS. Otherwise reply FAIL.

1. The answer states which SDK version it applies to.
2. Any code sample in the answer is syntactically valid Python.
3. Every SDK symbol named in the answer exists in the SDK.
4. Every HTTP endpoint path named in the answer exists in the API spec.
5. Deprecated v2 features are not recommended without a migration note.
6. A developer working in the SDK version the question is about would get
   correct, actionable guidance from this answer.

Reply in this format:

VERDICT: PASS
REASON: <one line>
```

- [ ] **Step 4: Write judge_v1.txt**

Create `results/week6/judge_v1.txt` — v0 with criteria 1–5 deleted:

```
You are grading an answer produced by a documentation assistant for the Relay SDK.

You will be shown the user's question, the documentation excerpts the assistant
retrieved, and the answer it produced.

Grade the answer against ONE criterion, and reply PASS or FAIL.

CRITERION: Would a developer working in the SDK version this question is about be able to act on this answer and get correct behaviour?

Do NOT consider any of the following. They are checked deterministically by
code before you ever see the answer, and re-judging them here would make your
verdict a noisy duplicate of a check that is already exact:

- whether code samples parse
- whether symbol or parameter names are spelled correctly or exist
- whether endpoint paths exist
- whether a version label is present anywhere in the text
- how citations are formatted

Judge only whether the guidance itself is correct and actionable for the
version the question is about. An answer that is fluent, well formatted and
confidently wrong about which version's behaviour it describes is a FAIL. A
refusal is a PASS only if the documentation genuinely does not contain the
answer.

Reply in exactly this format and nothing else:

VERDICT: PASS
REASON: <one line>
```

- [ ] **Step 5: Write the criterion reader**

Create `eval/week6/criterion.py`:

```python
"""Single source of truth for the judge's one criterion.

label.py shows the labeler this exact text and judge.py sends this exact text
to the model. Duplicating the sentence in two places would let the human and
the judge drift onto slightly different questions, and agreement between
answers to different questions is not agreement.
"""
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
WEEK6_RESULTS = REPO / "results" / "week6"

JUDGE_V0_PATH = WEEK6_RESULTS / "judge_v0.txt"
JUDGE_V1_PATH = WEEK6_RESULTS / "judge_v1.txt"
JUDGE_V2_PATH = WEEK6_RESULTS / "judge_v2.txt"

CRITERION_MARKER = "CRITERION:"


def read_criterion(path: Path) -> str:
    """The text after the single CRITERION: marker in a judge prompt."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(CRITERION_MARKER):
            return line.split(CRITERION_MARKER, 1)[1].strip()
    raise ValueError(f"{path} has no {CRITERION_MARKER} line")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_judge_prompts.py -v`
Expected: 7 PASS.

- [ ] **Step 7: Show the diff that is the deliverable**

Run: `diff results/week6/judge_v0.txt results/week6/judge_v1.txt`
Expected: criteria 1–5 gone, the do-not-consider block added. Keep this diff —
it is submission-checklist evidence.

- [ ] **Step 8: Commit**

```bash
git add results/week6/judge_v0.txt results/week6/judge_v1.txt eval/week6/criterion.py tests/test_week6_judge_prompts.py
git commit -m "week6: judge_v0 six criteria, judge_v1 with five deleted into assertions"
```

---

### Task 6: The frozen answer snapshot

**Files:**
- Modify: `rag/config.py`
- Modify: `rag/generator.py:143-160` (`answer_question`)
- Create: `eval/week6/snapshot.py`
- Test: `tests/test_week6_snapshot.py`

**Interfaces:**
- Consumes: `eval.week6.build_cases.load_cases()`, `rag.pipeline.RAGPipeline`, `rag.store.VectorStore`, `rag.generator.answer_question`
- Produces:
  - `rag.config.JUDGE_MODEL: str`
  - `rag.generator.answer_question(question, chunks, max_tokens=2048, threshold=..., model=None)` — `model=None` keeps the old behaviour
  - `eval.week6.snapshot.canonical_sha256(obj) -> str`
  - `eval.week6.snapshot.build_snapshot(cases: list[dict], resolve_fn, answer_fn) -> dict`
  - `eval.week6.snapshot.load_snapshot(path: Path | None = None) -> dict`
  - `eval.week6.snapshot.SNAPSHOT_PATH: Path` = `eval/raw/answers_25.json`

- [ ] **Step 1: Write the failing test**

Create `tests/test_week6_snapshot.py`:

```python
"""The frozen 25-answer snapshot.

Answers are generated ONCE and re-scored forever after. If they regenerated
per run, the 25 hand labels would silently decay and the
agreement_before -> agreement_after delta would mix judge changes with answer
drift, which would make the headline number of the whole week meaningless.
"""
import json

from eval.week6.snapshot import build_snapshot, canonical_sha256

CASES = [
    {
        "case_id": "W6-01",
        "question": "What is the default retry backoff?",
        "mode": "version-ambiguity",
        "origin": {"kind": "replay", "trace_id": "b84fe53eb006"},
        "version_sensitive": True,
        "sdk_version_intent": "unspecified",
        "retrieval": {"k": 4, "where": None, "strategy": "structural", "rerank": False},
        "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}},
        "replay_retrieved": [
            {
                "chunk_id": "v2:client:structural:2",
                "dense_distance": 0.51,
                "bm25_score": 19.0,
                "rrf_score": 0.0327,
                "rerank_score": None,
            }
        ],
        "notes": "",
    },
    {
        "case_id": "W6-02",
        "question": "Which error code means the token expired?",
        "mode": "clean",
        "origin": {"kind": "authored", "basis": "golden_set:Q3"},
        "version_sensitive": True,
        "sdk_version_intent": "v3",
        "retrieval": {"k": 4, "where": None, "strategy": "structural", "rerank": False},
        "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}},
        "replay_retrieved": None,
        "notes": "",
    },
]


def _resolve(case):
    return [
        {
            "chunk_id": "v3:errors:structural:1",
            "rank": 0,
            "text": "AUTH_TOKEN_EXPIRED means the bearer token is past its expiry.",
            "dense_distance": 0.2,
            "bm25_score": 9.0,
            "rrf_score": 0.03,
            "rerank_score": None,
            "metadata": {"source_file": "v3/errors.md", "sdk_version": "v3", "heading_path": "Errors"},
        }
    ]


def _answer(question, chunks, max_tokens, model):
    return f"answer to {question} [chunk: {chunks[0]['chunk_id']}]"


def test_snapshot_has_one_entry_per_case_carrying_its_mode():
    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)
    assert [a["case_id"] for a in snap["answers"]] == ["W6-01", "W6-02"]
    assert snap["answers"][0]["mode"] == "version-ambiguity"


def test_snapshot_records_the_retrieved_chunks_and_the_model_used():
    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)
    entry = snap["answers"][0]
    assert entry["retrieved"][0]["chunk_id"] == "v3:errors:structural:1"
    assert entry["model"] == "openai/gpt-oss-120b"
    assert entry["model_params"] == {"max_tokens": 2048}


def test_snapshot_flags_a_refusal():
    def refuse(question, chunks, max_tokens, model):
        return "I cannot answer that from the indexed documentation."

    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=refuse)
    assert snap["answers"][0]["refused"] is True


def test_answers_sha256_is_the_anchor_every_later_artifact_quotes():
    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)
    assert snap["answers_sha256"] == canonical_sha256(snap["answers"])


def test_answers_sha256_changes_when_any_answer_text_changes():
    a = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)

    def other(question, chunks, max_tokens, model):
        return "different text"

    b = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=other)
    assert a["answers_sha256"] != b["answers_sha256"]


def test_canonical_sha256_ignores_key_order():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_snapshot_is_json_serialisable():
    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)
    json.dumps(snap)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_snapshot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.week6.snapshot'`

- [ ] **Step 3: Add JUDGE_MODEL to config**

In `rag/config.py`, after the `GROQ_MODEL` line, add:

```python
# The judge runs on a different model than the answerer. A model grading its
# own family's output shows measurable self-preference, which would make the
# agreement figure partly a measure of family resemblance rather than of
# correctness.
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "llama-3.3-70b-versatile")
```

- [ ] **Step 4: Add the model override to answer_question**

In `rag/generator.py`, change the `answer_question` signature and body:

```python
def answer_question(
    question: str,
    chunks: list[dict],
    max_tokens: int = 2048,
    threshold: float = REFUSAL_DISTANCE_THRESHOLD,
    model: str | None = None,
) -> str:
    """Non-streaming answer, used by the CLI and the eval harness.

    model=None uses GROQ_MODEL. The override exists so a replayed trace can be
    answered by the model that produced it rather than by whatever the env
    happens to point at today.
    """
    if should_refuse(chunks, threshold):
        return REFUSAL_MESSAGE

    client = _get_client()
    completion = client.chat.completions.create(
        model=model or GROQ_MODEL,
        max_tokens=max_tokens,
        messages=_build_messages(question, chunks),
    )
    return completion.choices[0].message.content or ""
```

- [ ] **Step 5: Write the snapshot module**

Create `eval/week6/snapshot.py`:

```python
"""Generates the frozen 25-answer set that everything downstream scores.

Run once, deliberately. The one-command eval re-scores this file and never
regenerates it: the 25 hand labels describe THIS text, and the whole
agreement_before -> agreement_after comparison is only attributable to the
judge prompt if the answers underneath it hold still.

Replay cases resolve their chunks by chunk_id from the store using the scores
their trace logged (the same boundary eval/replay.py documents -- a trace
stores chunk ids, not chunk text). Authored cases retrieve live.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.week6.build_cases import load_cases
from rag.config import REFUSAL_MESSAGE
from rag.generator import PROMPT_VERSION, answer_question, extract_citations, verify_citations
from rag.pipeline import RAGPipeline, collection_for
from rag.store import VectorStore

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
SNAPSHOT_PATH = REPO / "eval" / "raw" / "answers_25.json"


def canonical_sha256(obj) -> str:
    """Hash of a JSON value, insensitive to key order."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def resolve_chunks(case: dict) -> list[dict]:
    """The chunks this case's answer is generated from.

    Replay cases rebuild the exact retrieved set the trace logged, so the
    answer is produced from the same evidence as the original failure.
    """
    strategy = case["retrieval"]["strategy"]
    if case["origin"]["kind"] == "replay":
        store = VectorStore(collection_name=collection_for(strategy))
        chunks = []
        for rank, record in enumerate(case["replay_retrieved"]):
            resolved = store.get_by_id(record["chunk_id"])
            if resolved is None:
                continue
            # The trace's own scores are reattached, not recomputed. Leaving
            # dense_distance as None would trip should_refuse(), which treats a
            # chunk carrying no dense distance as no evidence -- every replay
            # case would return the refusal string and reproduce nothing.
            chunks.append(
                {
                    **resolved,
                    "rank": rank,
                    "dense_distance": record["dense_distance"],
                    "bm25_score": record["bm25_score"],
                    "rrf_score": record["rrf_score"],
                    "rerank_score": record.get("rerank_score"),
                }
            )
        return chunks

    pipeline = RAGPipeline(strategy=strategy)
    return pipeline.retrieve(
        case["question"],
        k=case["retrieval"]["k"],
        where=case["retrieval"]["where"],
        rerank=case["retrieval"]["rerank"],
    )


def _call_answer(question: str, chunks: list[dict], max_tokens: int, model: str) -> str:
    return answer_question(question, chunks, max_tokens=max_tokens, model=model)


def build_snapshot(cases: list[dict], resolve_fn=resolve_chunks, answer_fn=_call_answer) -> dict:
    answers = []
    for case in cases:
        chunks = resolve_fn(case)
        started = time.monotonic()
        raw_output = answer_fn(
            case["question"],
            chunks,
            case["generation"]["model_params"]["max_tokens"],
            case["generation"]["model"],
        )
        latency_ms = (time.monotonic() - started) * 1000
        citation_check = verify_citations(raw_output, chunks)

        answers.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "mode": case["mode"],
                "version_sensitive": case["version_sensitive"],
                "sdk_version_intent": case["sdk_version_intent"],
                "origin": case["origin"],
                "retrieved": [
                    {
                        "chunk_id": c.get("chunk_id"),
                        "rank": c.get("rank"),
                        "dense_distance": c.get("dense_distance"),
                        "bm25_score": c.get("bm25_score"),
                        "rrf_score": c.get("rrf_score"),
                        "source_file": (c.get("metadata") or {}).get("source_file"),
                        "sdk_version": (c.get("metadata") or {}).get("sdk_version"),
                        "heading_path": (c.get("metadata") or {}).get("heading_path"),
                        "text": c.get("text", ""),
                    }
                    for c in chunks
                ],
                "raw_output": raw_output,
                "refused": raw_output.strip() == REFUSAL_MESSAGE,
                "citations": extract_citations(raw_output),
                "citation_check": citation_check,
                "prompt_version": PROMPT_VERSION,
                "model": case["generation"]["model"],
                "model_params": case["generation"]["model_params"],
                "latency_ms": round(latency_ms, 1),
                "answer_sha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "eval/week6/snapshot.py",
        "answers_sha256": canonical_sha256(answers),
        "answers": answers,
    }


def load_snapshot(path: Path | None = None) -> dict:
    return json.loads((path or SNAPSHOT_PATH).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--i-know-this-invalidates-labels",
        action="store_true",
        help="required to overwrite a snapshot once labels exist",
    )
    args = parser.parse_args()

    labels = BASE / "labels_25.json"
    if SNAPSHOT_PATH.exists() and labels.exists() and not args.i_know_this_invalidates_labels:
        raise SystemExit(
            f"{SNAPSHOT_PATH} already exists and {labels} was written against it.\n"
            "Regenerating would silently invalidate all 25 hand labels. Pass "
            "--i-know-this-invalidates-labels only if you intend to relabel from scratch."
        )

    snapshot = build_snapshot(load_cases())
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    refusals = sum(1 for a in snapshot["answers"] if a["refused"])
    print(f"wrote {SNAPSHOT_PATH}")
    print(f"answers: {len(snapshot['answers'])}  refusals: {refusals}")
    print(f"answers_sha256: {snapshot['answers_sha256']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_snapshot.py tests/test_generator.py tests/test_generator_grounding.py -v`
Expected: 7 new PASS, and both existing generator test files still PASS.
`tests/test_generator_grounding.py:69` calls `answer_question` positionally, so
the new `model=None` parameter must be appended last — demonstrate that rather
than assuming it.

- [ ] **Step 7: Commit**

```bash
git add rag/config.py rag/generator.py eval/week6/snapshot.py tests/test_week6_snapshot.py
git commit -m "week6: frozen answer snapshot, JUDGE_MODEL config, model override on answer_question"
```

---

### Task 7: Judge runner and the ordering guard

**Files:**
- Create: `eval/week6/judge.py`
- Test: `tests/test_week6_ordering.py`

**Interfaces:**
- Consumes: `eval.week6.criterion` paths, `eval.week6.snapshot.load_snapshot`, `rag.config.JUDGE_MODEL`
- Produces:
  - `OrderingError(Exception)`
  - `parse_verdict(raw: str) -> tuple[str, str]` — `("PASS"|"FAIL"|"UNPARSED", reason)`
  - `sha256_file(path: Path) -> str`
  - `require_committed_labels(labels_path: Path, repo: Path) -> dict` — `{"labels_commit", "labels_sha256"}`
  - `build_judge_messages(prompt_text: str, answer_rec: dict) -> list[dict]`
  - `run_judge(prompt_path, snapshot, labels_path, model, call_fn) -> dict`
  - `LABELS_PATH: Path`, `run_path_for(version: str) -> Path`

- [ ] **Step 1: Write the failing test**

Create `tests/test_week6_ordering.py`:

```python
"""The blind protocol, enforced in code.

The rubric scores the ORDER: 25 hand labels must provably predate the judge
run, and no ordering evidence means zero regardless of the numbers. So the
judge refuses to run against labels that are not committed, and every run
records the labels' commit hash and sha256 -- a hash that could only exist if
the labels were committed first.
"""
import json
import subprocess

import pytest

from eval.week6.judge import (
    OrderingError,
    build_judge_messages,
    parse_verdict,
    require_committed_labels,
    run_judge,
    sha256_file,
)


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    return tmp_path


def test_parse_verdict_reads_the_strict_contract():
    assert parse_verdict("VERDICT: PASS\nREASON: correct for v3") == ("PASS", "correct for v3")


def test_parse_verdict_reads_a_fail():
    assert parse_verdict("VERDICT: FAIL\nREASON: gives the v2 number")[0] == "FAIL"


def test_parse_verdict_refuses_to_guess_at_unparseable_output():
    """Coercing a rambling reply into PASS would silently invent agreement."""
    assert parse_verdict("I think this answer is pretty good overall!") == ("UNPARSED", "")


def test_parse_verdict_rejects_a_numeric_score():
    assert parse_verdict("SCORE: 7/10")[0] == "UNPARSED"


def test_guard_rejects_labels_that_were_never_committed(repo):
    labels = repo / "labels_25.json"
    labels.write_text("[]")
    with pytest.raises(OrderingError, match="not committed"):
        require_committed_labels(labels, repo)


def test_guard_rejects_labels_edited_since_their_commit(repo):
    labels = repo / "labels_25.json"
    labels.write_text('{"labels": []}')
    _git(repo, "add", "labels_25.json")
    _git(repo, "commit", "-qm", "labels")
    labels.write_text('{"labels": [{"case_id": "W6-01", "label": true}]}')
    with pytest.raises(OrderingError, match="modified since"):
        require_committed_labels(labels, repo)


def test_guard_accepts_committed_clean_labels_and_returns_the_proof(repo):
    labels = repo / "labels_25.json"
    labels.write_text('{"labels": []}')
    _git(repo, "add", "labels_25.json")
    _git(repo, "commit", "-qm", "labels")
    proof = require_committed_labels(labels, repo)
    assert len(proof["labels_commit"]) == 40
    assert proof["labels_sha256"] == sha256_file(labels)


def test_build_judge_messages_shows_question_chunks_and_answer():
    rec = {
        "question": "What is the default?",
        "retrieved": [{"chunk_id": "v3:client:structural:2", "source_file": "v3/client.md", "text": "2000 ms"}],
        "raw_output": "It is 2000 ms in v3.",
    }
    messages = build_judge_messages("PROMPT", rec)
    user = messages[1]["content"]
    assert "What is the default?" in user
    assert "v3:client:structural:2" in user
    assert "It is 2000 ms in v3." in user


def test_run_judge_records_the_labels_commit_as_ordering_proof(repo):
    labels = repo / "labels_25.json"
    labels.write_text('{"labels": []}')
    _git(repo, "add", "labels_25.json")
    _git(repo, "commit", "-qm", "labels")

    prompt = repo / "judge_v1.txt"
    prompt.write_text("CRITERION: Would a developer act on this?\nVERDICT:\nREASON:\n")

    snapshot = {
        "answers_sha256": "abc123",
        "answers": [
            {"case_id": "W6-01", "question": "q", "retrieved": [], "raw_output": "a"},
            {"case_id": "W6-02", "question": "q", "retrieved": [], "raw_output": "b"},
        ],
    }
    calls = []

    def fake_call(model, messages):
        calls.append(model)
        return "VERDICT: PASS\nREASON: fine"

    result = run_judge(prompt, snapshot, labels, "test-model", call_fn=fake_call)

    assert len(result["verdicts"]) == 2
    assert result["labels_commit"]
    assert result["labels_sha256"] == sha256_file(labels)
    assert result["answers_sha256"] == "abc123"
    assert calls == ["test-model", "test-model"]


def test_run_judge_refuses_before_making_a_single_model_call(repo):
    """The guard must run BEFORE the API calls, or an uncommitted-labels run
    still costs money and still leaves verdicts you have now seen."""
    labels = repo / "labels_25.json"
    labels.write_text("{}")
    prompt = repo / "judge_v1.txt"
    prompt.write_text("CRITERION: x\n")
    calls = []

    def fake_call(model, messages):
        calls.append(model)
        return "VERDICT: PASS\nREASON: fine"

    with pytest.raises(OrderingError):
        run_judge(prompt, {"answers_sha256": "x", "answers": [{"case_id": "W6-01", "question": "q", "retrieved": [], "raw_output": "a"}]}, labels, "m", call_fn=fake_call)
    assert calls == [], "no model call may happen before the ordering guard passes"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_ordering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.week6.judge'`

- [ ] **Step 3: Write the judge runner**

Create `eval/week6/judge.py`:

```python
"""Runs a judge prompt over the frozen snapshot, and refuses to run early.

The rubric scores the ordering, not just the numbers: hand labels must
provably predate the judge run. Timestamps are weak evidence -- anyone can
touch a file. So this module reads git, refuses when the labels file is
uncommitted or dirty, and stamps the labels' commit hash and sha256 into its
output. The resulting run file physically contains a hash that could only
exist if the labels were committed first.
"""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from eval.week6.criterion import JUDGE_V1_PATH, JUDGE_V2_PATH
from eval.week6.snapshot import load_snapshot
from rag.config import GROQ_API_KEY, JUDGE_MODEL

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
LABELS_PATH = BASE / "labels_25.json"
RAW_DIR = REPO / "eval" / "raw"

_VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(PASS|FAIL)\s*$", re.MULTILINE | re.IGNORECASE)
_REASON_RE = re.compile(r"^\s*REASON:\s*(.+)$", re.MULTILINE)

UNPARSED = "UNPARSED"


class OrderingError(Exception):
    """Raised when the blind protocol would be violated."""


def run_path_for(version: str) -> Path:
    return RAW_DIR / f"judge_{version}_run.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_verdict(raw: str) -> tuple[str, str]:
    """Strict parse. Anything that is not the contract is UNPARSED.

    Coercing a rambling reply into a PASS would invent agreement out of a
    formatting failure, which is the one error that would corrupt the headline
    number without leaving a trace.
    """
    match = _VERDICT_RE.search(raw)
    if match is None:
        return (UNPARSED, "")
    reason = _REASON_RE.search(raw)
    return (match.group(1).upper(), reason.group(1).strip() if reason else "")


def require_committed_labels(labels_path: Path, repo: Path) -> dict:
    """Proof that the labels predate this run, or refuse to run."""
    if not labels_path.exists():
        raise OrderingError(f"{labels_path} does not exist -- label before judging.")

    rel = labels_path.resolve().relative_to(repo.resolve()).as_posix()
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", rel],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not commit:
        raise OrderingError(
            f"{rel} is not committed. The blind protocol requires the labels to be "
            "committed BEFORE the judge runs -- an uncommitted file is not evidence "
            "of anything. Commit it on its own, then re-run."
        )

    dirty = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", rel], cwd=repo
    ).returncode
    if dirty != 0:
        raise OrderingError(
            f"{rel} has been modified since commit {commit[:12]}. Labels are frozen "
            "once committed: editing them to match the judge would move the ruler "
            "instead of the thing being measured."
        )

    return {"labels_commit": commit, "labels_sha256": sha256_file(labels_path)}


def build_judge_messages(prompt_text: str, answer_rec: dict) -> list[dict]:
    chunks = "\n\n".join(
        f"[chunk: {c.get('chunk_id')} | {c.get('source_file')}]\n{c.get('text', '')}"
        for c in answer_rec["retrieved"]
    ) or "(nothing retrieved)"
    user = (
        f"QUESTION:\n{answer_rec['question']}\n\n"
        f"RETRIEVED DOCUMENTATION:\n{chunks}\n\n"
        f"ANSWER UNDER REVIEW:\n{answer_rec['raw_output']}"
    )
    return [{"role": "system", "content": prompt_text}, {"role": "user", "content": user}]


def _groq_call(model: str, messages: list[dict]) -> str:
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model=model, messages=messages, temperature=0, max_tokens=256
    )
    return completion.choices[0].message.content or ""


def run_judge(
    prompt_path: Path,
    snapshot: dict,
    labels_path: Path,
    model: str,
    call_fn=_groq_call,
    repo: Path = REPO,
) -> dict:
    # The guard runs before the first model call. Checking afterwards would
    # still cost money and would still leave verdicts you have now seen.
    proof = require_committed_labels(labels_path, repo)
    prompt_text = prompt_path.read_text(encoding="utf-8")

    verdicts = []
    for rec in snapshot["answers"]:
        raw = call_fn(model, build_judge_messages(prompt_text, rec))
        verdict, reason = parse_verdict(raw)
        verdicts.append(
            {"case_id": rec["case_id"], "verdict": verdict, "reason": reason, "raw": raw}
        )

    return {
        "judge_prompt": prompt_path.as_posix(),
        "judge_prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        "judge_model": model,
        "temperature": 0,
        "answers_sha256": snapshot["answers_sha256"],
        "labels_commit": proof["labels_commit"],
        "labels_sha256": proof["labels_sha256"],
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdicts": verdicts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=("v1", "v2"), required=True)
    args = parser.parse_args()

    prompt_path = JUDGE_V1_PATH if args.version == "v1" else JUDGE_V2_PATH
    result = run_judge(prompt_path, load_snapshot(), LABELS_PATH, JUDGE_MODEL)

    out = run_path_for(args.version)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    counts = {}
    for v in result["verdicts"]:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    print(f"wrote {out}")
    print(f"verdicts: {counts}")
    print(f"labels_commit: {result['labels_commit']}  (ordering proof)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_ordering.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add eval/week6/judge.py tests/test_week6_ordering.py
git commit -m "week6: judge runner with the commit-order guard as ordering proof"
```

---

### Task 8: Agreement, confusion matrix and Cohen's kappa

**Files:**
- Create: `eval/week6/agreement.py`
- Test: `tests/test_week6_agreement.py`

**Interfaces:**
- Consumes: nothing (pure functions)
- Produces:
  - `cohens_kappa(tp: int, fp: int, fn: int, tn: int) -> float`
  - `compare(labels: list[dict], verdicts: list[dict], modes: dict[str, str]) -> dict` returning `{"n", "matches", "agreement", "confusion", "kappa", "human_pass_rate", "unparsed", "disagreements", "by_mode"}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_week6_agreement.py`:

```python
"""Agreement between the human labels and the judge.

Raw agreement alone is not enough to trust. With a skewed label set a judge
that answers PASS unconditionally scores high while never reading anything --
the same "one pooled number hides it" failure the task warns about, one level
up. Cohen's kappa is reported next to the percentage so that judge is visible.
"""
from eval.week6.agreement import cohens_kappa, compare

MODES = {"W6-01": "clean", "W6-02": "clean", "W6-03": "version-ambiguity", "W6-04": "version-ambiguity"}


def _labels(*values):
    return [{"case_id": f"W6-0{i+1}", "label": v} for i, v in enumerate(values)]


def _verdicts(*values):
    return [{"case_id": f"W6-0{i+1}", "verdict": v, "reason": "r"} for i, v in enumerate(values)]


def test_perfect_agreement_is_one_hundred_percent():
    result = compare(_labels(True, False), _verdicts("PASS", "FAIL"), MODES)
    assert result["matches"] == 2
    assert result["agreement"] == 1.0


def test_total_disagreement_is_zero_percent():
    result = compare(_labels(True, False), _verdicts("FAIL", "PASS"), MODES)
    assert result["agreement"] == 0.0


def test_confusion_matrix_uses_the_human_label_as_reference():
    result = compare(
        _labels(True, True, False, False), _verdicts("PASS", "FAIL", "PASS", "FAIL"), MODES
    )
    assert result["confusion"] == {"tp": 1, "fn": 1, "fp": 1, "tn": 1}


def test_disagreements_name_the_case_the_mode_and_both_opinions():
    result = compare(_labels(True, True), _verdicts("PASS", "FAIL"), MODES)
    assert len(result["disagreements"]) == 1
    d = result["disagreements"][0]
    assert d["case_id"] == "W6-02"
    assert d["human"] is True
    assert d["judge"] == "FAIL"
    assert d["mode"] == "clean"


def test_agreement_is_broken_out_per_mode():
    result = compare(
        _labels(True, True, True, True), _verdicts("PASS", "PASS", "FAIL", "FAIL"), MODES
    )
    assert result["by_mode"]["clean"]["agreement"] == 1.0
    assert result["by_mode"]["version-ambiguity"]["agreement"] == 0.0


def test_an_unparsed_verdict_counts_as_a_disagreement_not_a_free_pass():
    result = compare(_labels(True), _verdicts("UNPARSED"), MODES)
    assert result["matches"] == 0
    assert result["unparsed"] == 1


def test_kappa_is_one_for_perfect_agreement():
    assert cohens_kappa(tp=10, fp=0, fn=0, tn=10) == 1.0


def test_kappa_exposes_a_judge_that_always_says_pass():
    """22 of 25 labels are PASS, so a judge that never reads anything and
    always says PASS scores 88% raw agreement. Kappa says 0."""
    result = compare(
        _labels(*([True] * 22 + [False] * 3)), _verdicts(*(["PASS"] * 25)), {}
    )
    assert round(result["agreement"], 2) == 0.88
    assert round(result["kappa"], 3) == 0.0


def test_kappa_is_zero_when_expected_agreement_is_total():
    assert cohens_kappa(tp=25, fp=0, fn=0, tn=0) == 0.0


def test_compare_requires_the_same_case_ids_on_both_sides():
    import pytest

    with pytest.raises(ValueError, match="case_id"):
        compare(_labels(True), _verdicts("PASS", "PASS"), MODES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_agreement.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.week6.agreement'`

- [ ] **Step 3: Write the implementation**

Create `eval/week6/agreement.py`:

```python
"""Human-vs-judge agreement.

Reports raw agreement (the two numbers the task asks for) alongside the
confusion matrix and Cohen's kappa. Kappa is not decoration: on a skewed label
set, a judge that answers PASS unconditionally scores high raw agreement while
never reading anything, and only kappa makes that visible.
"""


def cohens_kappa(tp: int, fp: int, fn: int, tn: int) -> float:
    """Agreement corrected for the agreement two coin-flips would reach."""
    n = tp + fp + fn + tn
    if n == 0:
        return 0.0

    observed = (tp + tn) / n
    human_pass = (tp + fn) / n
    judge_pass = (tp + fp) / n
    expected = human_pass * judge_pass + (1 - human_pass) * (1 - judge_pass)

    if expected >= 1.0:
        return 0.0
    return (observed - expected) / (1 - expected)


def compare(labels: list[dict], verdicts: list[dict], modes: dict[str, str]) -> dict:
    label_by_case = {row["case_id"]: bool(row["label"]) for row in labels}
    verdict_by_case = {row["case_id"]: row["verdict"] for row in verdicts}

    if set(label_by_case) != set(verdict_by_case):
        missing = set(label_by_case) ^ set(verdict_by_case)
        raise ValueError(f"case_id mismatch between labels and verdicts: {sorted(missing)}")

    tp = fp = fn = tn = 0
    unparsed = 0
    matches = 0
    disagreements = []
    by_mode: dict[str, dict] = {}

    for case_id in sorted(label_by_case):
        human = label_by_case[case_id]
        judge = verdict_by_case[case_id]
        mode = modes.get(case_id, "unknown")

        # An unparseable verdict is a disagreement, never a free pass -- the
        # judge failed to answer the question it was asked.
        if judge not in ("PASS", "FAIL"):
            unparsed += 1
            agreed = False
        else:
            judge_pass = judge == "PASS"
            agreed = judge_pass == human
            if human and judge_pass:
                tp += 1
            elif human and not judge_pass:
                fn += 1
            elif not human and judge_pass:
                fp += 1
            else:
                tn += 1

        bucket = by_mode.setdefault(mode, {"n": 0, "matches": 0, "agreement": 0.0})
        bucket["n"] += 1
        if agreed:
            matches += 1
            bucket["matches"] += 1
        else:
            disagreements.append(
                {"case_id": case_id, "mode": mode, "human": human, "judge": judge}
            )

    for bucket in by_mode.values():
        bucket["agreement"] = bucket["matches"] / bucket["n"] if bucket["n"] else 0.0

    n = len(label_by_case)
    return {
        "n": n,
        "matches": matches,
        "agreement": matches / n if n else 0.0,
        "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        "kappa": cohens_kappa(tp, fp, fn, tn),
        "human_pass_rate": sum(label_by_case.values()) / n if n else 0.0,
        "unparsed": unparsed,
        "disagreements": disagreements,
        "by_mode": dict(sorted(by_mode.items())),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_agreement.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add eval/week6/agreement.py tests/test_week6_agreement.py
git commit -m "week6: agreement, confusion matrix and Cohen's kappa"
```

---

### Task 9: The blind labeling CLI

**Files:**
- Create: `eval/week6/label.py`
- Test: `tests/test_week6_label.py`

**Interfaces:**
- Consumes: `eval.week6.criterion.read_criterion`/`sha256_text`/`JUDGE_V1_PATH`, `eval.week6.snapshot.load_snapshot`, `eval.week6.judge.run_path_for`
- Produces:
  - `BlindnessError(Exception)`
  - `ensure_blind(run_paths: list[Path], force: bool) -> bool`
  - `render_case(answer_rec: dict, index: int, total: int) -> str`
  - `build_labels_file(criterion: str, answers_sha256: str, rows: list[dict], blind: bool) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_week6_label.py`:

```python
"""The labeling CLI, and the two properties that make it blind.

It imports nothing from judge.py's verdict data and refuses to run once a
judge run exists. Labeling after reading the judge's verdicts is not
validation -- it is agreeing with yourself with extra steps.
"""
import pytest

from eval.week6.label import (
    BlindnessError,
    build_labels_file,
    ensure_blind,
    render_case,
)

REC = {
    "case_id": "W6-07",
    "question": "What's the default retry backoff for Client.send()?",
    "mode": "version-ambiguity",
    "retrieved": [
        {"chunk_id": "v2:client:structural:2", "source_file": "v2/client.md", "text": "default 500 ms"},
        {"chunk_id": "v3:client:structural:2", "source_file": "v3/client.md", "text": "default 2000 ms"},
    ],
    "raw_output": "The default is 500 ms.",
}


def test_ensure_blind_allows_labeling_before_any_judge_run(tmp_path):
    assert ensure_blind([tmp_path / "judge_v1_run.json"], force=False) is True


def test_ensure_blind_refuses_once_a_judge_run_exists(tmp_path):
    run = tmp_path / "judge_v1_run.json"
    run.write_text("{}")
    with pytest.raises(BlindnessError, match="already been run"):
        ensure_blind([run], force=False)


def test_force_relabel_is_allowed_but_marks_the_file_as_not_blind(tmp_path):
    run = tmp_path / "judge_v1_run.json"
    run.write_text("{}")
    assert ensure_blind([run], force=True) is False


def test_render_case_shows_the_question_chunks_and_answer():
    text = render_case(REC, 1, 25)
    assert "1/25" in text
    assert "W6-07" in text
    assert "v2:client:structural:2" in text
    assert "The default is 500 ms." in text


def test_render_case_never_shows_the_mode_tag():
    """Knowing a case was filed under "version-ambiguity" tells the labeler
    what to look for and biases the label toward the taxonomy."""
    assert "version-ambiguity" not in render_case(REC, 1, 25)


def test_labels_file_records_the_criterion_and_the_answers_hash():
    rows = [{"case_id": "W6-07", "label": False, "seconds": 41, "note": "v2 number"}]
    out = build_labels_file("Would a developer act on this?", "abc123", rows, blind=True)
    assert out["criterion_text"] == "Would a developer act on this?"
    assert out["criterion_sha256"]
    assert out["answers_sha256"] == "abc123"
    assert out["blind"] is True
    assert out["labels"] == rows


def test_a_forced_relabel_is_self_incriminating_in_the_file():
    out = build_labels_file("c", "abc", [], blind=False)
    assert out["blind"] is False


def test_label_module_does_not_import_judge_verdicts():
    """Structural guarantee, not a promise: there is no code path by which a
    verdict could reach the labeler's screen."""
    import inspect

    import eval.week6.label as label

    source = inspect.getsource(label)
    assert "verdict" not in source.lower()
    assert "run_judge" not in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_label.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.week6.label'`

- [ ] **Step 3: Write the labeling CLI**

Create `eval/week6/label.py`:

```python
"""Blind labeling: 25 answers, one binary criterion, no judge output anywhere.

Two properties make this blind rather than nominally blind. First, this module
never reads a judge run's contents -- there is no code path by which the
judge's opinion could reach the screen. Second, it refuses to run at all once
a judge run file exists, unless forced, and a forced run stamps
"blind": false into its own output.

The criterion shown here is read out of judge_v1.txt rather than duplicated,
so the human and the judge cannot end up answering slightly different
questions. Seeing the criterion is correct and necessary; seeing the judge's
answers is not.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eval.week6.criterion import JUDGE_V1_PATH, read_criterion, sha256_text
from eval.week6.judge import LABELS_PATH, run_path_for
from eval.week6.snapshot import load_snapshot


class BlindnessError(Exception):
    """Raised when labeling would no longer be blind."""


def ensure_blind(run_paths: list[Path], force: bool) -> bool:
    """Return whether this session is blind, refusing if it is not and not forced."""
    existing = [p for p in run_paths if p.exists()]
    if not existing:
        return True
    if force:
        return False
    raise BlindnessError(
        f"The judge has already been run ({', '.join(p.name for p in existing)}). "
        "Labeling now would not be blind -- you would be agreeing with a verdict "
        "you have already seen. Pass --force-relabel only if you accept that the "
        "output will be marked blind=false."
    )


def render_case(answer_rec: dict, index: int, total: int) -> str:
    """One case, as the labeler sees it.

    Deliberately omits the mode tag: telling the labeler this case was filed
    under "version-ambiguity" would tell them what to look for.
    """
    chunks = "\n".join(
        f"  [{c.get('chunk_id')}] {c.get('source_file')}: {' '.join((c.get('text') or '').split())[:160]}"
        for c in answer_rec["retrieved"]
    ) or "  (nothing retrieved)"
    return (
        f"\n{'=' * 78}\n"
        f"CASE {index}/{total}  {answer_rec['case_id']}\n"
        f"{'=' * 78}\n"
        f"QUESTION:\n  {answer_rec['question']}\n\n"
        f"RETRIEVED:\n{chunks}\n\n"
        f"ANSWER:\n{answer_rec['raw_output']}\n"
        f"{'-' * 78}\n"
    )


def build_labels_file(
    criterion: str, answers_sha256: str, rows: list[dict], blind: bool
) -> dict:
    return {
        "criterion_text": criterion,
        "criterion_sha256": sha256_text(criterion),
        "answers_sha256": answers_sha256,
        "blind": blind,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "labels": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labeler", required=True, help="who is labeling, recorded in the file")
    parser.add_argument("--force-relabel", action="store_true")
    args = parser.parse_args()

    blind = ensure_blind([run_path_for("v1"), run_path_for("v2")], args.force_relabel)

    snapshot = load_snapshot()
    criterion = read_criterion(JUDGE_V1_PATH)
    answers = snapshot["answers"]

    print("\nYou are labeling on ONE binary criterion:\n")
    print(f"  {criterion}\n")
    print("  y = yes (PASS)   n = no (FAIL)   ? = show the case again   q = save and quit\n")
    print("Answer only that question. Code syntax, symbol spelling, endpoint")
    print("existence, version-label presence and citation formatting are all")
    print("checked by code -- ignore them here.\n")

    rows = []
    for index, rec in enumerate(answers, start=1):
        print(render_case(rec, index, len(answers)))
        while True:
            choice = input("  label [y/n/?/q]: ").strip().lower()
            if choice == "?":
                print(render_case(rec, index, len(answers)))
                continue
            if choice == "q":
                print(f"\nStopping early with {len(rows)}/{len(answers)} labeled.")
                _write(args.labeler, criterion, snapshot, rows, blind)
                return
            if choice in ("y", "n"):
                note = input("  note (optional): ").strip()
                rows.append(
                    {"case_id": rec["case_id"], "label": choice == "y", "note": note}
                )
                break
            print("  please answer y, n, ? or q")

    _write(args.labeler, criterion, snapshot, rows, blind)


def _write(labeler: str, criterion: str, snapshot: dict, rows: list[dict], blind: bool) -> None:
    payload = build_labels_file(criterion, snapshot["answers_sha256"], rows, blind)
    payload["labeler"] = labeler
    LABELS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    passes = sum(1 for r in rows if r["label"])
    print(f"\nwrote {LABELS_PATH}")
    print(f"labels: {len(rows)}  pass: {passes}  fail: {len(rows) - passes}  blind: {blind}")
    print("\nNEXT: commit this file ON ITS OWN before running the judge:")
    print("  git add eval/week6/labels_25.json")
    print('  git commit -m "week6: 25 blind labels (pre-judge)"')


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_label.py -v`
Expected: 8 PASS.

If `test_label_module_does_not_import_judge_verdicts` fails, the module gained
a reference to verdict data — remove it rather than relaxing the test. That
test is the structural guarantee behind the whole 25-point criterion.

- [ ] **Step 5: Commit**

```bash
git add eval/week6/label.py tests/test_week6_label.py
git commit -m "week6: blind labeling CLI with the blindness guard"
```

---

### Task 10: The one command

**Files:**
- Create: `eval/week6/run.py`
- Create: `eval/week6/report.py`
- Modify: `README.md`
- Test: `tests/test_week6_run.py`

**Interfaces:**
- Consumes: everything from Tasks 1–9
- Produces:
  - `eval.week6.run.score_cases(snapshot, cases, specs) -> list[dict]` — rows of `{"case_id", "mode", "assertions", "assertions_ok"}`
  - `eval.week6.run.mode_table(rows, verdicts) -> dict`
  - `eval.week6.run.build_report(...) -> dict`
  - `eval.week6.report.render(report: dict) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_week6_run.py`:

```python
"""The one command's arithmetic.

Pass rate is reported per mode and never pooled: an average will happily hide
a total regression on the version-confusion mode while the clean mode carries
the number.
"""
from eval.week6.run import mode_table, score_cases

SPECS = {
    "symbols": {"retry_backoff_ms": {"kind": "parameter", "versions": ["v3"], "sources": []}},
    "openapi": {"paths": {"/v3/auth/token": {"post": {}}}},
    "deprecations": [],
}

CASES = [
    {"case_id": "W6-01", "mode": "clean", "version_sensitive": True},
    {"case_id": "W6-02", "mode": "version-ambiguity", "version_sensitive": True},
]

SNAPSHOT = {
    "answers": [
        {"case_id": "W6-01", "mode": "clean", "raw_output": "In v3, `retry_backoff_ms` is 2000 ms."},
        {"case_id": "W6-02", "mode": "version-ambiguity", "raw_output": "It is 500 ms."},
    ]
}


def test_score_cases_runs_all_five_assertions_per_case():
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    assert len(rows) == 2
    assert len(rows[0]["assertions"]) == 5


def test_a_case_with_a_failing_assertion_is_not_assertions_ok():
    rows = {r["case_id"]: r for r in score_cases(SNAPSHOT, CASES, SPECS)}
    assert rows["W6-01"]["assertions_ok"] is True
    assert rows["W6-02"]["assertions_ok"] is False, "no v2/v3 named, so A4 fails"


def test_mode_table_reports_each_mode_separately():
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    verdicts = [
        {"case_id": "W6-01", "verdict": "PASS", "reason": ""},
        {"case_id": "W6-02", "verdict": "PASS", "reason": ""},
    ]
    table = mode_table(rows, verdicts)
    assert table["clean"]["overall"] == 1
    assert table["version-ambiguity"]["overall"] == 0, "assertion failure blocks the pass"


def test_overall_pass_needs_both_the_assertions_and_the_judge():
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    verdicts = [
        {"case_id": "W6-01", "verdict": "FAIL", "reason": ""},
        {"case_id": "W6-02", "verdict": "PASS", "reason": ""},
    ]
    table = mode_table(rows, verdicts)
    assert table["clean"]["assertions_ok"] == 1
    assert table["clean"]["judge_pass"] == 0
    assert table["clean"]["overall"] == 0


def test_mode_table_works_with_no_judge_run_at_all():
    """--no-judge must still produce the assertion half of the table so the
    deterministic checks can be run without an API key."""
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    table = mode_table(rows, verdicts=None)
    assert table["clean"]["assertions_ok"] == 1
    assert table["clean"]["judge_pass"] is None
    assert table["clean"]["overall"] is None


def test_skipped_assertions_never_count_as_passes():
    """A3 applies to almost no case. If skipped counted as pass it would
    donate free passes and manufacture a pass rate out of nothing."""
    rows = score_cases(SNAPSHOT, CASES, SPECS)
    a3 = next(a for a in rows[0]["assertions"] if a["id"].startswith("A3"))
    assert a3["status"] == "skipped"
    counts = mode_table(rows, verdicts=None)["clean"]
    assert counts["assertion_pass_counts"]["A3_endpoints_exist"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_week6_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eval.week6.run'`

- [ ] **Step 3: Write run.py**

Create `eval/week6/run.py`:

```python
"""THE one command: python -m eval.week6.run

Scores the frozen snapshot with the five deterministic assertions, folds in
whichever judge runs exist, and prints pass rate BY MODE. Never pooled into a
single headline: the average would hide a total regression on the
version-confusion mode while the clean mode carried the number.
"""
import argparse
import json
from pathlib import Path

from eval.spec import load_specs
from eval.week6 import report
from eval.week6.agreement import compare
from eval.week6.assertions import ASSERTION_IDS, FAIL, PASS, assertions_ok, run_assertions
from eval.week6.build_cases import MODES, load_cases
from eval.week6.judge import LABELS_PATH, run_path_for
from eval.week6.snapshot import load_snapshot

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
OUT_JSON = REPO / "eval" / "raw" / "week6.json"
OUT_MD = REPO / "results" / "week6-results.md"

# judge_v0 asked six questions; five became assertions and one stayed.
JUDGE_V0_CRITERIA = 6
JUDGED_CRITERIA = 1


def score_cases(snapshot: dict, cases: list[dict], specs: dict) -> list[dict]:
    case_by_id = {c["case_id"]: c for c in cases}
    rows = []
    for rec in snapshot["answers"]:
        case = case_by_id[rec["case_id"]]
        results = run_assertions(rec["raw_output"], case, specs)
        rows.append(
            {
                "case_id": rec["case_id"],
                "mode": rec["mode"],
                "assertions": results,
                "assertions_ok": assertions_ok(results),
            }
        )
    return rows


def mode_table(rows: list[dict], verdicts: list[dict] | None) -> dict:
    verdict_by_case = {v["case_id"]: v["verdict"] for v in (verdicts or [])}
    table: dict = {}

    for row in rows:
        bucket = table.setdefault(
            row["mode"],
            {
                "n": 0,
                "assertions_ok": 0,
                "judge_pass": 0 if verdicts else None,
                "overall": 0 if verdicts else None,
                "assertion_pass_counts": {aid: 0 for aid in ASSERTION_IDS},
                "assertion_fail_counts": {aid: 0 for aid in ASSERTION_IDS},
            },
        )
        bucket["n"] += 1
        if row["assertions_ok"]:
            bucket["assertions_ok"] += 1

        for result in row["assertions"]:
            # skipped increments neither counter: an assertion that did not run
            # is not a pass.
            if result["status"] == PASS:
                bucket["assertion_pass_counts"][result["id"]] += 1
            elif result["status"] == FAIL:
                bucket["assertion_fail_counts"][result["id"]] += 1

        if verdicts:
            judged_pass = verdict_by_case.get(row["case_id"]) == "PASS"
            if judged_pass:
                bucket["judge_pass"] += 1
            if judged_pass and row["assertions_ok"]:
                bucket["overall"] += 1

    return table


def build_report(snapshot, cases, specs, judge_runs: dict, labels: dict | None) -> dict:
    rows = score_cases(snapshot, cases, specs)
    modes = {rec["case_id"]: rec["mode"] for rec in snapshot["answers"]}

    agreements = {}
    for version, run in judge_runs.items():
        if labels is None:
            continue
        agreements[version] = compare(labels["labels"], run["verdicts"], modes)

    primary = judge_runs.get("v2") or judge_runs.get("v1")
    return {
        "n_cases": len(rows),
        "answers_sha256": snapshot["answers_sha256"],
        "assertion_count": len(ASSERTION_IDS),
        "judged_criteria_count": JUDGED_CRITERIA,
        "judge_v0_criteria_count": JUDGE_V0_CRITERIA,
        "by_mode": mode_table(rows, primary["verdicts"] if primary else None),
        "rows": rows,
        "judge_runs": {
            version: {
                "judge_prompt": run["judge_prompt"],
                "judge_model": run["judge_model"],
                "labels_commit": run["labels_commit"],
                "labels_sha256": run["labels_sha256"],
                "run_at": run["run_at"],
            }
            for version, run in judge_runs.items()
        },
        "agreement": agreements,
    }


def _print_mode_table(rep: dict) -> None:
    print(f"\n=== Pass rate by mode (n={rep['n_cases']}) ===")
    print(f"{'mode':<22}{'n':>3}{'assert':>9}{'judge':>8}{'overall':>10}")
    totals = {"n": 0, "assertions_ok": 0, "judge_pass": 0, "overall": 0}
    has_judge = any(b["judge_pass"] is not None for b in rep["by_mode"].values())

    for mode in MODES:
        bucket = rep["by_mode"].get(mode)
        if bucket is None:
            continue
        n = bucket["n"]
        a = bucket["assertions_ok"]
        j = bucket["judge_pass"]
        o = bucket["overall"]
        totals["n"] += n
        totals["assertions_ok"] += a
        if has_judge:
            totals["judge_pass"] += j or 0
            totals["overall"] += o or 0
        j_txt = f"{j}/{n}" if j is not None else "-"
        o_txt = f"{o}/{n} {o / n:.0%}" if o is not None else "-"
        print(f"{mode:<22}{n:>3}{f'{a}/{n}':>9}{j_txt:>8}{o_txt:>10}")

    print("-" * 52)
    n = totals["n"]
    o_txt = f"{totals['overall']}/{n} {totals['overall'] / n:.0%}" if has_judge else "-"
    j_txt = f"{totals['judge_pass']}/{n}" if has_judge else "-"
    print(f"{'TOTAL':<22}{n:>3}{f'{totals["assertions_ok"]}/{n}':>9}{j_txt:>8}{o_txt:>10}")

    print("\n=== Assertions vs judged criteria ===")
    print(
        f"deterministic assertions: {rep['assertion_count']}    "
        f"judged criteria: {rep['judged_criteria_count']}    "
        f"(judge_v0 had {rep['judge_v0_criteria_count']})"
    )

    if rep["agreement"]:
        print("\n=== Judge agreement with the 25 human labels ===")
        for version in ("v1", "v2"):
            agr = rep["agreement"].get(version)
            if agr is None:
                continue
            name = "agreement_before" if version == "v1" else "agreement_after "
            commit = rep["judge_runs"][version]["labels_commit"][:12]
            print(
                f"{name} (judge_{version}): {agr['agreement']:.0%}  "
                f"kappa {agr['kappa']:.2f}  "
                f"matches {agr['matches']}/{agr['n']}  "
                f"[labels commit {commit}]"
            )
        print("\nkappa is reported next to the percentage because on a skewed label")
        print("set a judge that always answers PASS scores high agreement while")
        print("never reading anything.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-judge", action="store_true", help="assertions only, no API key needed")
    args = parser.parse_args()

    snapshot = load_snapshot()
    cases = load_cases()
    specs = load_specs()

    judge_runs = {}
    if not args.no_judge:
        for version in ("v1", "v2"):
            path = run_path_for(version)
            if path.exists():
                judge_runs[version] = json.loads(path.read_text(encoding="utf-8"))

    labels = None
    if LABELS_PATH.exists():
        labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))

    rep = build_report(snapshot, cases, specs, judge_runs, labels)
    _print_mode_table(rep)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rep, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(report.render(rep), encoding="utf-8")
    print(f"\nwrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write report.py**

Create `eval/week6/report.py`:

```python
"""Renders results/week6-results.md from eval/raw/week6.json.

Generated, never hand-edited -- the repo's existing convention (see
eval/report.py). Editing the markdown instead of the renderer is how a
write-up and its data start to disagree.
"""
from eval.week6.build_cases import MODES


def render(rep: dict) -> str:
    lines = [
        "# Week 6 — Validating the docs-answer judge",
        "",
        "Generated by `python -m eval.week6.run`. Do not edit by hand —",
        "edit `eval/week6/report.py` and re-run.",
        "",
        f"Frozen answer set: `{rep['answers_sha256'][:16]}…` over {rep['n_cases']} cases.",
        "",
        "## Pass rate by mode",
        "",
        "| Mode | n | assertions ok | judge pass | overall |",
        "|---|---|---|---|---|",
    ]

    for mode in MODES:
        bucket = rep["by_mode"].get(mode)
        if bucket is None:
            continue
        n = bucket["n"]
        judge = f"{bucket['judge_pass']}/{n}" if bucket["judge_pass"] is not None else "—"
        overall = (
            f"{bucket['overall']}/{n} ({bucket['overall'] / n:.0%})"
            if bucket["overall"] is not None
            else "—"
        )
        lines.append(f"| `{mode}` | {n} | {bucket['assertions_ok']}/{n} | {judge} | {overall} |")

    lines += [
        "",
        "Reported per mode and never pooled: an average hides a total regression",
        "on one mode while another carries the number.",
        "",
        "## Assertions vs judged criteria",
        "",
        f"- deterministic assertions: **{rep['assertion_count']}**",
        f"- judged criteria: **{rep['judged_criteria_count']}**",
        f"- judge_v0 judged **{rep['judge_v0_criteria_count']}** criteria before the split",
        "",
    ]

    if rep["agreement"]:
        lines += ["## Judge agreement with the 25 blind human labels", ""]
        for version in ("v1", "v2"):
            agr = rep["agreement"].get(version)
            if agr is None:
                continue
            run = rep["judge_runs"][version]
            name = "agreement_before" if version == "v1" else "agreement_after"
            lines += [
                f"### {name} — `judge_{version}`",
                "",
                f"- agreement: **{agr['agreement']:.0%}** ({agr['matches']}/{agr['n']})",
                f"- Cohen's kappa: **{agr['kappa']:.2f}**",
                f"- human PASS rate: {agr['human_pass_rate']:.0%}",
                f"- confusion (human as reference): {agr['confusion']}",
                f"- unparsed verdicts: {agr['unparsed']}",
                f"- labels commit (ordering proof): `{run['labels_commit']}`",
                f"- labels sha256: `{run['labels_sha256'][:16]}…`",
                f"- judge model: `{run['judge_model']}`",
                "",
                "Disagreements:",
                "",
            ]
            for d in agr["disagreements"]:
                human = "PASS" if d["human"] else "FAIL"
                lines.append(
                    f"- `{d['case_id']}` (`{d['mode']}`) — human {human}, judge {d['judge']}"
                )
            lines.append("")

    # Disclosed rather than buried: both of these limit how much the two
    # headline percentages can carry, and a reader who does not know them will
    # over-read a small move.
    lines += [
        "## Caveats on these numbers",
        "",
        f"- **Single run, not a reproducible one.** Groq is not bit-deterministic "
        f"even at temperature 0, so a re-run can shift a verdict or two. Every "
        f"figure here comes from one recorded run, and the raw model responses "
        f"are kept in `eval/raw/judge_*_run.json`.",
        f"- **{rep['n_cases']} cases is a small denominator.** One flipped verdict "
        f"moves agreement by {1 / rep['n_cases']:.0%}. A move of that size is not "
        f"signal.",
        "- **judge_v2 saw two of these cases as examples.** They stay inside the "
        "headline denominator, because excluding them would be self-scoring. "
        "`results/week6/disagreements.md` reports agreement over the "
        "non-few-shot cases separately, which is the number that shows what "
        "generalised.",
        "",
    ]

    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_week6_run.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Run the whole suite**

Run: `venv/bin/python -m pytest -q`
Expected: every test passes, including the pre-existing week 3/4/5 tests.

- [ ] **Step 7: Document the command in README.md**

Append this section to `README.md`, after the "Week 3 evaluation" section:

```markdown
## Week 6 evaluation — validating the judge

```bash
python -m eval.week6.run              # the one command: pass rate by mode
python -m eval.week6.run --no-judge   # assertions only, no API key needed
```

Scores a frozen 25-answer snapshot (`eval/raw/answers_25.json`) with five
deterministic assertions and, when they exist, the judge runs. Prints pass
rate **by mode** — never pooled — plus the assertion/judged-criteria counts
and human agreement before and after the judge iteration.

The protocol is ordered, and the order is the evidence:

```bash
python -m eval.week6.snapshot                              # generate the frozen answers, once
python -m eval.week6.label --labeler "<you>"               # 25 blind labels
git add eval/week6/labels_25.json && git commit             # MUST come before the judge run
python -m eval.week6.judge --version v1                    # refuses if the labels are uncommitted
python -m eval.week6.judge --version v2
```

`eval/week6/judge.py` reads `git log` and will not make a single model call
against labels that are not committed and clean. Each run records the labels'
commit hash and sha256, so the run file itself proves the labels came first:

```bash
git log --oneline --reverse -- eval/week6/labels_25.json eval/raw/judge_v1_run.json
jq -r .labels_commit eval/raw/judge_v1_run.json
```

`results/week6-results.md` is generated. Edit `eval/week6/report.py` and
re-run, never the markdown.
```

- [ ] **Step 8: Commit**

```bash
git add eval/week6/run.py eval/week6/report.py tests/test_week6_run.py README.md
git commit -m "week6: one-command eval with per-mode pass rate and agreement reporting"
```

---

### Task 11: Commit C1 and generate the frozen snapshot

**Files:**
- Generate: `eval/raw/answers_25.json`

**Interfaces:**
- Consumes: everything from Tasks 1–10
- Produces: the frozen answer set that Task 12 labels

- [ ] **Step 1: Confirm the index holds the whole corpus**

The `cross-product-bleed` cases only reproduce if the second product and the
PDFs are indexed alongside `v2`/`v3`, exactly as they were when the traces were
logged.

Run:

```bash
venv/bin/python cli.py status
```

Expected: a non-zero chunk count. If it is empty or only holds the version
trees, run `venv/bin/python cli.py ingest data/documents` to index the full
corpus (including `OMNUMI_SDK_IOS_DOCUMENTATION.md` and the two PDFs).

- [ ] **Step 2: Confirm the API key is present**

Run: `venv/bin/python -c "from rag.config import GROQ_API_KEY, GROQ_MODEL, JUDGE_MODEL; print(bool(GROQ_API_KEY), GROQ_MODEL, JUDGE_MODEL)"`
Expected: `True openai/gpt-oss-120b llama-3.3-70b-versatile`

- [ ] **Step 3: Verify everything is green and committed**

Run: `venv/bin/python -m pytest -q && git status --porcelain`
Expected: all tests pass; working tree clean (Tasks 1–10 are all committed).

- [ ] **Step 4: Generate the snapshot**

Run: `venv/bin/python -m eval.week6.snapshot`
Expected output shape:

```
wrote .../eval/raw/answers_25.json
answers: 25  refusals: <N>
answers_sha256: <64 hex chars>
```

- [ ] **Step 5: Sanity-check the snapshot before labeling against it**

Run:

```bash
venv/bin/python -c "
import json
s = json.load(open('eval/raw/answers_25.json'))
print('answers:', len(s['answers']))
empty = [a['case_id'] for a in s['answers'] if not a['raw_output'].strip()]
print('empty answers:', empty)
nochunks = [a['case_id'] for a in s['answers'] if not a['retrieved']]
print('cases with no retrieved chunks:', nochunks)
replay_refusals = [a['case_id'] for a in s['answers']
                   if a['origin']['kind'] == 'replay' and a['refused']]
print('replay cases that refused:', replay_refusals)
from collections import Counter
print('by mode:', Counter(a['mode'] for a in s['answers']))
"
```

Expected: 25 answers, no empty answers, five per mode. A case with no
retrieved chunks means a replay chunk_id no longer resolves in the index —
fix that before labeling, because relabeling later is not an option.

`replay cases that refused` should list at most `W6-16` (trace `132709d13774`
refused originally too, so a refusal there is faithful reproduction). If the
other three replay cases refuse, their logged `dense_distance` values are not
reaching `should_refuse` — check `resolve_chunks`, do not lower the threshold.

- [ ] **Step 6: Run the assertion half with no judge**

Run: `venv/bin/python -m eval.week6.run --no-judge`
Expected: the per-mode table with an `assert` column and `-` under judge and
overall. This confirms the assertions run over real answers before any human
or model time is spent.

- [ ] **Step 7: Commit C1**

```bash
git add eval/raw/answers_25.json eval/raw/week6.json results/week6-results.md
git commit -m "week6 C1: frozen 25-answer snapshot + assertion-only baseline"
```

---

### Task 12: Commit C2 — the human labeling session

**Files:**
- Create: `eval/week6/labels_25.json`

**Interfaces:**
- Consumes: `eval/raw/answers_25.json`, `results/week6/judge_v1.txt`
- Produces: the committed labels every later artifact is measured against

> **This task is performed by the human, not by an agent.** An agent must stop
> here and hand over. Model-produced labels would make the "agreement with a
> human" figure a measure of family resemblance between two models, which is
> the exact thing this week exists to test rather than assume.

- [ ] **Step 1: Confirm no judge has run**

Run: `ls eval/raw/judge_v1_run.json eval/raw/judge_v2_run.json 2>/dev/null || echo "no judge run yet - good"`
Expected: `no judge run yet - good`. If either file exists, the blind protocol
is already broken and the labeling tool will refuse.

- [ ] **Step 2: Label all 25**

Run: `venv/bin/python -m eval.week6.label --labeler "ajithkumar.palani@softsuave.com"`

For each case, answer only this: *would a developer working in the SDK version
this question is about be able to act on this answer and get correct
behaviour?* `y` or `n`.

Ignore code syntax, symbol spelling, endpoint existence, whether a version
label is present, and citation formatting — all five are checked by code.

Write a short note on any case you found hard. Those notes are what make the
disagreement analysis in Task 13 possible.

Expected on completion:

```
wrote .../eval/week6/labels_25.json
labels: 25  pass: <N>  fail: <25-N>  blind: True
```

- [ ] **Step 3: Verify the file records a blind session**

Run:

```bash
venv/bin/python -c "
import json
d = json.load(open('eval/week6/labels_25.json'))
print('labels:', len(d['labels']), 'blind:', d['blind'])
print('answers_sha256 matches snapshot:',
      d['answers_sha256'] == json.load(open('eval/raw/answers_25.json'))['answers_sha256'])
print('criterion:', d['criterion_text'][:70])
"
```

Expected: `labels: 25`, `blind: True`, `answers_sha256 matches snapshot: True`.

- [ ] **Step 4: Commit C2 — the labels alone**

Nothing else may go in this commit. It is the ordering evidence, and a commit
that also touches code is a weaker artifact to point at.

```bash
git add eval/week6/labels_25.json
git status --short   # confirm ONLY labels_25.json is staged
git commit -m "week6 C2: 25 blind labels (pre-judge)"
git rev-parse HEAD   # paste this hash into the write-up
```

- [ ] **Step 5: Do not touch the labels again**

From here the file is frozen. Task 13's checks assert its sha256 still matches
what the judge run recorded — changing a label to agree with the judge would
move the ruler instead of the thing being measured.

---

### Task 13: Commit C3 — judge_v1, agreement_before, and the disagreement analysis

**Files:**
- Generate: `eval/raw/judge_v1_run.json`
- Create: `results/week6/disagreements.md`

**Interfaces:**
- Consumes: committed `labels_25.json`, `judge_v1.txt`, the frozen snapshot
- Produces: `agreement_before`, and the two disagreements Task 15 uses as few-shots

- [ ] **Step 1: Run judge_v1**

Run: `venv/bin/python -m eval.week6.judge --version v1`
Expected:

```
wrote .../eval/raw/judge_v1_run.json
verdicts: {'PASS': <N>, 'FAIL': <M>}
labels_commit: <40 hex chars>  (ordering proof)
```

If it raises `OrderingError`, the labels are uncommitted or dirty. That is the
guard working — commit them (Task 12 step 4) and re-run. Do not bypass it.

- [ ] **Step 2: Verify the ordering proof chain**

Run:

```bash
git log --oneline --reverse -- eval/week6/labels_25.json eval/raw/judge_v1_run.json
jq -r .labels_commit eval/raw/judge_v1_run.json
git rev-parse HEAD~0 --short
sha256sum eval/week6/labels_25.json
jq -r .labels_sha256 eval/raw/judge_v1_run.json
```

Expected: the labels commit appears first in the log; `labels_commit` matches
the C2 hash; the two sha256 values are identical. **This output is the
evidence for the 25-point criterion — paste it into the write-up.**

- [ ] **Step 3: Read agreement_before**

Run: `venv/bin/python -m eval.week6.run`
Expected: the per-mode table plus

```
agreement_before (judge_v1): __%  kappa __  matches __/25  [labels commit ...]
```

Record both numbers. If kappa is far below the raw agreement, say so in the
write-up — it means the label set is skewed and the percentage flatters the
judge.

- [ ] **Step 4: List the disagreements with everything needed to adjudicate them**

Run:

```bash
venv/bin/python -c "
import json
rep = json.load(open('eval/raw/week6.json'))
snap = {a['case_id']: a for a in json.load(open('eval/raw/answers_25.json'))['answers']}
labels = {l['case_id']: l for l in json.load(open('eval/week6/labels_25.json'))['labels']}
verdicts = {v['case_id']: v for v in json.load(open('eval/raw/judge_v1_run.json'))['verdicts']}
for d in rep['agreement']['v1']['disagreements']:
    cid = d['case_id']
    print('=' * 78)
    print(cid, '|', d['mode'], '| human', 'PASS' if d['human'] else 'FAIL', '| judge', d['judge'])
    print('Q:', snap[cid]['question'])
    print('retrieved:', [c['chunk_id'] for c in snap[cid]['retrieved']])
    print('your note:', labels[cid].get('note') or '(none)')
    print('judge reason:', verdicts[cid]['reason'])
    print('--- answer ---')
    print(snap[cid]['raw_output'][:1200])
"
```

- [ ] **Step 5: Write the disagreement analysis**

Create `results/week6/disagreements.md`. At least 2 entries — the rubric wants
a verdict on **who was right**, not a description of the difference. Use this
structure per entry, filling in from step 4's output:

```markdown
# judge_v1 disagreements with the 25 blind human labels

agreement_before: __% (__/25), Cohen's kappa __
Labels commit (pre-judge): `<C2 hash>`

## 1. `W6-__` — mode `<mode>`

**Question:** <the question>
**Retrieved:** <chunk_ids>
**My label:** PASS / FAIL — <the note I wrote while labeling>
**Judge verdict:** PASS / FAIL — "<judge reason>"

**Answer excerpt:**

> <the part that decides it>

**Who was right:** <me / the judge>, because <the reason, argued from the
retrieved chunks and not from which side is more flattering>.

**What this says about the prompt:** <the specific instruction that was
missing or misread>.

## 2. `W6-__` — mode `<mode>`

<same structure>

## Where the disagreements cluster

<which modes they fall in — a disagreement concentrated in one mode is a
prompt gap; disagreements scattered evenly are noise.>
```

Be honest in the "who was right" line. Cases where the judge was right and the
label was sloppy are the most informative entries here, and the rubric asks for
a verdict, not a defence.

- [ ] **Step 6: Commit C3**

```bash
git add eval/raw/judge_v1_run.json eval/raw/week6.json results/week6-results.md results/week6/disagreements.md
git commit -m "week6 C3: judge_v1 run, agreement_before, disagreement analysis"
```

---

### Task 14: Commit C4 — the prediction, before any iteration

**Files:**
- Create: `results/week6/prediction.txt`

**Interfaces:**
- Consumes: the disagreement analysis from Task 13
- Produces: the falsifiable claim Task 15 is scored against

> **The human writes this.** It must be committed before `judge_v2.txt` exists.

- [ ] **Step 1: Confirm judge_v2 does not exist yet**

Run: `ls results/week6/judge_v2.txt 2>/dev/null && echo "TOO LATE - v2 already written" || echo "v2 not written yet - good"`
Expected: `v2 not written yet - good`

- [ ] **Step 2: Write the prediction**

Create `results/week6/prediction.txt`. One sentence, with numbers, falsifiable:

```
Week 6 prediction — dated 2026-09-__ (before judge_v2 was written)

Adding W6-__ and W6-__ (both <mode>) to judge_v1 as few-shot examples will
raise agreement from __% to at least __% by fixing the <specific behaviour,
e.g. "judge accepting an answer that states v3 while quoting v2's default">,
and will not change the verdict on any <other mode> case.

Falsified if: agreement lands below __%, or any <other mode> case flips
verdict, or either few-shot case still disagrees.
```

Replace every blank with a real value from Task 13's numbers. A prediction
you cannot be wrong about scores nothing — the "will not change the verdict
on any other mode case" clause is what makes this one checkable.

- [ ] **Step 3: Commit C4 — the prediction alone**

```bash
git add results/week6/prediction.txt
git status --short   # confirm ONLY prediction.txt is staged
git commit -m "week6 C4: prediction before judge iteration"
git rev-parse HEAD
```

---

### Task 15: Commit C5 — judge_v2, agreement_after, and the write-up

**Files:**
- Create: `results/week6/judge_v2.txt`
- Generate: `eval/raw/judge_v2_run.json`, `eval/raw/week6.json`, `results/week6-results.md`
- Modify: `results/week6/disagreements.md`
- Test: `tests/test_week6_ordering.py`

**Interfaces:**
- Consumes: `judge_v1.txt`, the two adjudicated disagreements, the committed prediction
- Produces: `agreement_after` and the final write-up

- [ ] **Step 1: Write judge_v2.txt**

Copy `results/week6/judge_v1.txt` to `results/week6/judge_v2.txt`, keep the
`CRITERION:` line byte-identical, and insert a few-shot block before the
output-format section. Use the two cases you adjudicated in Task 13 — real
text from the snapshot, not invented examples:

```
Two worked examples, both taken from real disagreements on this criterion:

EXAMPLE 1
QUESTION: <W6-__ question>
ANSWER: <the deciding excerpt of the real answer>
VERDICT: FAIL
REASON: <why, in the terms the criterion uses>

EXAMPLE 2
QUESTION: <W6-__ question>
ANSWER: <the deciding excerpt of the real answer>
VERDICT: PASS
REASON: <why>
```

Keep the `CRITERION:` line unchanged. Changing the criterion would mean the
human labels no longer answer the same question, and agreement_after would not
be comparable to agreement_before.

- [ ] **Step 2: Verify v2 is v1 plus examples, nothing else**

Run: `diff results/week6/judge_v1.txt results/week6/judge_v2.txt`
Expected: only the few-shot block added. If the criterion line differs, fix it
— the comparison depends on it.

Run: `venv/bin/python -m pytest tests/test_week6_judge_prompts.py -v`
Expected: still PASS — v2 must not reintroduce any asserted criterion.

- [ ] **Step 3: Run judge_v2**

Run: `venv/bin/python -m eval.week6.judge --version v2`
Expected: `wrote .../eval/raw/judge_v2_run.json` plus the verdict counts and
the same `labels_commit` as v1's run.

- [ ] **Step 4: Read agreement_after**

Run: `venv/bin/python -m eval.week6.run`
Expected both lines:

```
agreement_before (judge_v1): __%  kappa __  ...
agreement_after  (judge_v2): __%  kappa __  ...
```

- [ ] **Step 5: Add the anti-relabelling test**

Append to `tests/test_week6_ordering.py`:

```python
def test_the_committed_labels_were_never_edited_after_the_judge_ran():
    """The task's sharpest trap: reaching a higher agreement by relabelling
    the cases you disagreed on moves the ruler, not the thing being measured.
    This makes that mechanically detectable instead of a matter of conscience.
    """
    import json
    from pathlib import Path

    from eval.week6.judge import LABELS_PATH, run_path_for, sha256_file

    if not LABELS_PATH.exists():
        pytest.skip("labels not written yet")

    for version in ("v1", "v2"):
        path = run_path_for(version)
        if not path.exists():
            continue
        recorded = json.loads(path.read_text(encoding="utf-8"))["labels_sha256"]
        assert recorded == sha256_file(LABELS_PATH), (
            f"labels_25.json changed since judge_{version} ran"
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_week6_ordering.py -v`
Expected: 11 PASS. A failure here means the labels were edited after a judge
run — restore them from commit C2 (`git checkout <C2-hash> -- eval/week6/labels_25.json`)
rather than re-running the judge.

- [ ] **Step 7: Score the prediction honestly**

Append to `results/week6/disagreements.md`:

```markdown
## Prediction, scored

**Predicted** (committed <C4 hash>, before judge_v2 existed): <paste the
sentence from prediction.txt>

**Actual:** agreement __% -> __%, kappa __ -> __.

**Where the prediction was right:** <...>

**Where it was wrong:** <...>

Agreement over the 23 cases NOT used as few-shot examples: __%. The two
few-shot cases are kept inside the headline denominator — excluding them
would be self-scoring — but they are nearly guaranteed to agree, so this
second number is what shows how much of the delta generalised.
```

Compute the 23-case number with:

```bash
venv/bin/python -c "
import json, sys
FEWSHOT = {'W6-__', 'W6-__'}  # the two case_ids used as examples
labels = {l['case_id']: bool(l['label']) for l in json.load(open('eval/week6/labels_25.json'))['labels']}
verdicts = {v['case_id']: v['verdict'] for v in json.load(open('eval/raw/judge_v2_run.json'))['verdicts']}
rest = [c for c in labels if c not in FEWSHOT]
m = sum(1 for c in rest if (verdicts[c] == 'PASS') == labels[c])
print(f'agreement over {len(rest)} non-few-shot cases: {m}/{len(rest)} = {m/len(rest):.0%}')
"
```

Report the "wrong" section even when it is uncomfortable. The rubric scores the
prediction being honestly scored, not the prediction being right.

- [ ] **Step 8: Full suite and final verification**

Run: `venv/bin/python -m pytest -q`
Expected: everything passes.

Run: `venv/bin/python -m eval.week6.run`
Expected: the complete table with both agreement lines.

- [ ] **Step 9: Commit C5**

```bash
git add results/week6/judge_v2.txt results/week6/disagreements.md eval/raw/judge_v2_run.json eval/raw/week6.json results/week6-results.md tests/test_week6_ordering.py
git commit -m "week6 C5: judge_v2 with two disagreement few-shots, agreement_after, results"
```

- [ ] **Step 10: Verify the full ordering chain one last time**

Run:

```bash
git log --oneline --reverse --format='%h %ad %s' --date=short -- \
  eval/week6/labels_25.json eval/raw/judge_v1_run.json \
  results/week6/prediction.txt results/week6/judge_v2.txt
```

Expected order: `labels_25.json` → `judge_v1_run.json` → `prediction.txt` →
`judge_v2.txt`. That sequence is the submission's central evidence — paste it
into the write-up.

---

## Submission checklist mapping

| Required artifact | Path | Produced in |
|---|---|---|
| `labels_25.json` + the hash proving it predates the judge run | `eval/week6/labels_25.json`, `labels_commit` in `eval/raw/judge_v1_run.json` | Tasks 12, 13 |
| `judge_v1.txt` and `judge_v2.txt`, diffed, with the 2 disagreements visible in v2 | `results/week6/judge_v1.txt`, `judge_v2.txt` | Tasks 5, 15 |
| `prediction.txt`, written before iterating | `results/week6/prediction.txt` | Task 14 |
| Terminal output of the single eval command with pass rate by mode | `python -m eval.week6.run` | Task 10 |
| `agreement_before` / `agreement_after` | `results/week6-results.md`, `eval/raw/week6.json` | Tasks 13, 15 |
| Assertion count vs judged criteria count | 5 vs 1 (v0 had 6), printed by `run.py` | Task 10 |
| Note on 2 disagreements naming who was right | `results/week6/disagreements.md` | Tasks 13, 15 |
