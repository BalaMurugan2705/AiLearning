"""Loads the Week 7 race artifacts (results/week7/*.csv, *.json, *.md, *.log)
into plain data structures for the /week7 dashboard route in app.py.

Kept dependency-free from FastAPI/Jinja2 on purpose -- this module only
reads and shapes data, so it's testable without spinning up the web app.
"""
import csv
import json
import re
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "week7"

# Order matters -- this is the order sections appear in the dashboard.
RACE_SETS = [
    {"key": "assignment", "label": "10-Question Assignment Race", "csv": "race.csv", "details": "race_details.json"},
    {"key": "easy", "label": "Golden Set: Easy (15 questions)", "csv": "race_easy.csv", "details": "race_details_easy.json"},
    {"key": "medium", "label": "Golden Set: Medium (15 questions)", "csv": "race_medium.csv", "details": "race_details_medium.json"},
    {"key": "hard", "label": "Golden Set: Hard (15 questions)", "csv": "race_hard.csv", "details": "race_details_hard.json"},
]


def _read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_text_file(name: str) -> str | None:
    path = RESULTS_DIR / name
    return path.read_text() if path.exists() else None


def load_race_sets() -> list[dict]:
    """One entry per race that actually has a race.csv on disk (hard is
    skipped this run, so it's simply absent rather than shown empty).
    """
    sets = []
    for spec in RACE_SETS:
        rows = _read_csv_rows(RESULTS_DIR / spec["csv"])
        if not rows:
            continue
        sets.append(
            {
                "key": spec["key"],
                "label": spec["label"],
                "rows": rows,
                "questions": _load_question_breakdown(spec["details"]),
            }
        )
    return sets


def _load_question_breakdown(details_filename: str) -> list[dict]:
    """Merge agent + workflow per-question records into one row per
    question, so the dashboard can show both systems side by side.
    """
    data = _read_json(RESULTS_DIR / details_filename)
    if not data:
        return []

    by_id: dict[str, dict] = {}
    for system in ("agent", "workflow"):
        for record in data.get(system, []):
            row = by_id.setdefault(
                record["id"],
                {
                    "id": record["id"],
                    "question": record["question"],
                    "needs_chain": record.get("needs_chain", False),
                },
            )
            row[f"{system}_passed"] = record["passed"]
            row[f"{system}_answer"] = record.get("answer")
            row[f"{system}_budget_reason"] = record.get("budget_reason")

    return [by_id[key] for key in sorted(by_id.keys())]


_INLINE_PATTERNS = [
    (re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)"), r"<em>\1</em>"),
]


def _inline(text: str) -> str:
    for pattern, replacement in _INLINE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def render_markdown(text: str) -> str:
    """Minimal, dependency-free renderer for exactly the subset of Markdown
    results/week7/verdict.md actually uses: #/## headers, **bold**,
    *italics*, `code`, and "- " bullets. Table rows (lines starting with
    "|") are skipped -- the dashboard renders those numbers as real HTML
    tables from the CSVs instead, not by parsing markdown tables.
    """
    html_parts: list[str] = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            html_parts.append("</ul>")
            in_list = False

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            close_list()
            continue
        if stripped.startswith("## "):
            close_list()
            html_parts.append(f"<h3>{_inline(stripped[3:])}</h3>")
        elif stripped.startswith("# "):
            continue  # page already has its own title
        elif stripped.startswith("|"):
            continue  # rendered as real tables from CSV data instead
        elif stripped.startswith("- "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{_inline(stripped[2:])}</li>")
        else:
            close_list()
            html_parts.append(f"<p>{_inline(stripped)}</p>")

    close_list()
    return "\n".join(html_parts)
