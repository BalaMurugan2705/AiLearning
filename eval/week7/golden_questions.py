"""Converts the existing human-authored golden sets
(data/documents/input_files/golden_sets/{gs_easy,gs_medium,gs_hard}.json)
into the race harness's question schema, instead of hand-writing a new set.

Every non-negative fragment below was chosen by reading that entry's own
golden `answer` field -- not auto-extracted -- because a naive "last quoted
span in the answer" heuristic silently picks the WRONG term on several
entries. Two examples that would have broken silently:
  - medium#05: "The 'asyncio' library option was added alongside the
    default 'urllib3'." The last quote is 'urllib3', but that's the OLD
    default being contrasted, not the new fact the question asks for.
  - hard#05: ends with "...nest these under an 'additionalProperties'
    block", but 'additionalProperties' is a generic key shared with
    hard#03's fact -- the actually-required migration step is 'webclient'.

Negative-case entries (metadata.is_negative_case: true) have no fact to
grade against -- they exist to check the system admits "not in the docs"
instead of fabricating. Grading (including refusal detection) lives in
eval/week7/run_race.py's grade_entry(), not here -- this module only loads
and shapes the data.
"""
import json
from pathlib import Path

GOLDEN_SETS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "documents" / "input_files" / "golden_sets"
)

_LEVEL_FILES = {"easy": "gs_easy", "medium": "gs_medium", "hard": "gs_hard"}

# id -> hand-picked expected_fragment, one entry per non-negative question.
_FRAGMENTS = {
    "easy": {
        "01": "markdown",
        "02": "io.swagger.codegen.v3",
        "03": "okhttp-gson",
        "04": "400 KB",
        "05": "1.0.0",
        "06": "true",
        "07": "public_repo",
        "08": "io.swagger",
        "09": "false",
        "10": "swagger_client",
        "11": "false",
        "12": "201 Created",
    },
    "medium": {
        "01": "assignees",
        "02": "--generate-markdown",
        "03": "no override",
        "04": ["unconditionally", "regardless of"],
        "05": "asyncio",
        "06": "parse error",
        "07": "internal",
        "08": "-DhideGenerationTimestamp=true",
        "09": "discussion_category_name",
        "10": "--verbose",
        "11": "useOneOfInterfaces",
        "12": "default branch",
    },
    "hard": {
        "01": "owner",
        "02": "negation",
        "03": "additionalProperties",
        "04": "maintainer_can_modify",
        "05": "webclient",
        "06": "make_latest",
        "07": "markdown table",
        "08": "pre-armed",
        "09": "wrap_tables",
        "10": "asyncio",
        "11": "at creation",
        "12": "--generate-markdown",
    },
}


def _needs_chain(entry: dict) -> bool:
    metadata = entry["metadata"]
    if metadata.get("is_negative_case"):
        return False
    target_file = metadata.get("target_file")
    api_version = metadata.get("api_version") or metadata.get("api_versions")
    if isinstance(target_file, list) or isinstance(api_version, list):
        return True
    question = entry["question"]
    return "2022-11-28" in question and "2025-06-01" in question


def load_golden_set(level: str) -> list[dict]:
    """level is one of 'easy', 'medium', 'hard'."""
    filename = _LEVEL_FILES[level]
    raw = json.loads((GOLDEN_SETS_DIR / f"{filename}.json").read_text())

    questions = []
    for entry in raw:
        is_negative = bool(entry["metadata"].get("is_negative_case"))
        questions.append(
            {
                "id": f"{level}-{entry['id']}",
                "question": entry["question"],
                "is_negative_case": is_negative,
                "expected_fragment": None if is_negative else _FRAGMENTS[level][entry["id"]],
                "needs_chain": _needs_chain(entry),
            }
        )
    return questions
