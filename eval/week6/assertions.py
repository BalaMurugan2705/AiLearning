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
