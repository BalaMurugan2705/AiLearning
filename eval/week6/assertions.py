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

# `\b` after the tag group rejects "pycon" (a REPL transcript, not python
# source -- its `>>>` prompts fail ast.parse) while still admitting a fenced
# header like ```python title="x". A bare `\s*` in place of `[^\n]*` would
# reject both; only the word boundary tells "py" + non-word from "py" + "con".
_PY_FENCE_OPEN_RE = re.compile(r"```(?:python|py)\b[^\n]*\n")
_PY_FENCE_RE = re.compile(r"```(?:python|py)\b[^\n]*\n(.*?)```", re.DOTALL)
_ANY_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# Accepts "v3", "V3", "version 3", "Version 3" -- LLM prose capitalises at
# sentence start and sometimes spells the word out, and a regex that only
# catches the terse form manufactures false FAILs on correct answers.
_VERSION_RE = re.compile(r"\bv(?:ersion)?\s?[23]\b", re.IGNORECASE)

# Trace citations are shaped `[chunk: v3:client:structural:2]` (ASCII) or
# `【chunk: v3:client:structural:2】` (full-width, seen in this project's
# traces). Both embed a version tag that is metadata about *where the answer's
# claim was retrieved from*, not the answer *stating* which version it
# describes -- and nearly every answer carries one, so leaving it unstripped
# would make A4 pass almost everything regardless of what the prose says.
_CITATION_RE = re.compile(r"\[chunk:[^\]]*\]|【chunk:[^】]*】")


def _result(assertion_id: str, status: str, detail: str) -> dict:
    return {"id": assertion_id, "status": status, "detail": detail}


def strip_code_fences(answer: str) -> str:
    """Answer prose with fenced code blocks removed.

    A2 scans prose only. Local variable names a code sample invents
    (`my_client`, `raw_payload`) are not SDK symbols, and checking them
    against the symbol table would fail on perfectly good examples.
    """
    return _ANY_FENCE_RE.sub("\n", answer)


def _version_scan_text(answer: str) -> str:
    """Prose A4 scans: code fences and citation markers stripped out.

    Composes `strip_code_fences` with citation removal. Without stripping
    citations too, a chunk id like `[chunk: v2:client:structural:2]` would
    satisfy `_VERSION_RE` even when the answer's own prose never says which
    version it means -- exactly the failure mode A4 exists to catch.
    """
    return _CITATION_RE.sub(" ", strip_code_fences(answer))


def assert_code_parses(answer: str) -> dict:
    """A1: every closed python fence in the answer survives ast.parse.

    An opening ```python line with no matching closing fence is not "no code
    sample" -- with max_tokens=2048 in this harness, truncation mid-fence is
    a live failure mode, and a truncated sample is exactly the broken code
    A1 exists to catch. So opens are counted separately from closed fences:
    more opens than closes means FAIL, not SKIPPED.
    """
    opens = _PY_FENCE_OPEN_RE.findall(answer)
    if not opens:
        return _result(A1, SKIPPED, "answer contains no python fence")

    fences = _PY_FENCE_RE.findall(answer)
    if len(opens) > len(fences):
        return _result(
            A1, FAIL, "unterminated python fence: truncated before closing ```"
        )

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
    """A4: a version-sensitive answer must name v2 or v3 explicitly, in prose.

    Checks stated-ness only, and only in text the reader actually reads as
    prose -- see `_version_scan_text`. Whether the named version is the
    RIGHT one is a judgement and stays with the judge -- that is the seam
    between the deterministic half and the judged half.
    """
    if not version_sensitive:
        return _result(A4, SKIPPED, "case is not version-sensitive")

    found = _VERSION_RE.findall(_version_scan_text(answer))
    if found:
        # Dedupe case-insensitively ("v3" and "V3" are the same statement)
        # while keeping the first-seen spelling for the detail string.
        unique = {}
        for match in found:
            unique.setdefault(match.lower(), match)
        ordered = sorted(unique.values(), key=str.lower)
        return _result(A4, PASS, f"states {', '.join(ordered)}")
    return _result(A4, FAIL, "no v2/v3 named anywhere in the answer")


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
