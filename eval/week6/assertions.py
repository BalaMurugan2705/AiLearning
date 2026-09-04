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
