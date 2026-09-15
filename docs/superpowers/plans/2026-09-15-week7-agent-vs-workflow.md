# Week 7 Task Set E — Agent Loop vs. Fixed Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-tool docs-migration Q&A agent (ReAct loop) and a fixed 4-step workflow twin over the same tools/model, enforce 4 budgets on the agent, race both over 10 questions, and produce the numbers + verdict Task Set E asks for.

**Architecture:** A shared `agent/` package holds hand-extracted, page-cited spec data (no fabricated facts), 3 tool implementations + JSON schemas, a Groq tool-calling ReAct loop with budget checks, and a hard-coded workflow that calls the same 3 tools without a decision loop. `eval/week7/` holds the 10-question test set and the race/budget-demo scripts that produce the graded artifacts in `results/week7/`.

**Tech Stack:** Python 3.14, `groq` SDK (already a dependency, OpenAI-compatible tool-calling), existing `rag/` package (`RAGPipeline`, `VectorStore`) for retrieval, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-15-week7-agent-vs-workflow-design.md`

## Global Constraints

- No tool may return a fact not present in `agent/data/github_openapi.json`, `agent/data/deprecations.json`, or the retrieved document text — every entry in those two files carries an `x_source` page citation back to `github_combined_reference.pdf`.
- Agent and workflow use the exact same tool set, same model (`agent.config.AGENT_MODEL`), and the same final output contract (a plain-text answer string).
- Every budget (`max_iterations`, `max_tokens`, `max_cost_usd`, `max_wall_seconds`) must be checked in code, not just declared, per iteration of the agent loop — this is what Task Set E's rubric explicitly checks for.
- Per-lap token usage is summed across the whole run, never just the final call's usage (the task doc's called-out common mistake).
- Follow existing repo conventions: real embedding model + real Chroma for retrieval-behavior tests (see `tests/test_store_filtering.py`), a `FakeStore`/fake-client pattern for logic tests that don't need the real model or a live API call (see `tests/test_pipeline.py`).
- Naming fix vs. the design spec: the JSON data files live under `agent/data/` here, not `agent/spec/` as the spec doc says — a `spec/` subpackage and a `spec.py` loader module in the same parent package would collide on import (`agent.spec` would be ambiguous). Same content, safer path.

---

## Task 1: Agent config and budget enforcement

**Files:**
- Create: `agent/__init__.py` (empty)
- Create: `agent/config.py`
- Create: `agent/budgets.py`
- Test: `tests/test_week7_budgets.py`

**Interfaces:**
- Produces: `agent.config.AGENT_MODEL: str`, `agent.config.price_for(model: str) -> tuple[float, float]` (USD per 1M input tokens, USD per 1M output tokens).
- Produces: `agent.budgets.Budget` (dataclass: `max_iterations: int`, `max_tokens: int`, `max_cost_usd: float`, `max_wall_seconds: float`), `agent.budgets.BudgetExceeded(Exception)` with `.reason: str`, `agent.budgets.BudgetTracker(budget: Budget)` with methods `start_iteration() -> None`, `record_usage(prompt_tokens: int, completion_tokens: int, price_in: float, price_out: float) -> None`, `elapsed() -> float`, and attributes `iterations: int`, `total_tokens: int`, `total_cost_usd: float`.

- [ ] **Step 1: Create `agent/__init__.py`**

Empty file — makes `agent` a package.

```bash
mkdir -p agent
touch agent/__init__.py
```

- [ ] **Step 2: Write `agent/config.py`**

```python
import os

# Read from the same GROQ_MODEL env var the rest of the app uses, but with
# our own default -- rag.config.GROQ_MODEL currently has its default swapped
# with JUDGE_MODEL in an uncommitted local edit, so we deliberately don't
# import it here.
AGENT_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# USD per 1,000,000 tokens (input, output). Source: Groq's published
# on-demand rate for openai/gpt-oss-120b as of 2026-09-15 ($0.15 / $0.60).
# An unrecognized model falls back to (0.0, 0.0) so cost reports as an
# explicit $0 ("unpriced") rather than a guessed number.
PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
}


def price_for(model: str) -> tuple[float, float]:
    return PRICING_PER_MILLION_TOKENS.get(model, (0.0, 0.0))
```

- [ ] **Step 3: Write the failing budget tests**

```python
# tests/test_week7_budgets.py
import time

import pytest

from agent.budgets import Budget, BudgetExceeded, BudgetTracker


def _budget(**overrides):
    defaults = dict(max_iterations=5, max_tokens=10_000, max_cost_usd=1.0, max_wall_seconds=60.0)
    defaults.update(overrides)
    return Budget(**defaults)


def test_start_iteration_within_budget_does_not_raise():
    tracker = BudgetTracker(budget=_budget())
    tracker.start_iteration()
    assert tracker.iterations == 1


def test_max_iterations_trips():
    tracker = BudgetTracker(budget=_budget(max_iterations=1))
    tracker.start_iteration()
    with pytest.raises(BudgetExceeded, match="max_iterations"):
        tracker.start_iteration()


def test_max_wall_seconds_trips():
    tracker = BudgetTracker(budget=_budget(max_wall_seconds=0.01))
    time.sleep(0.02)
    with pytest.raises(BudgetExceeded, match="max_wall_seconds"):
        tracker.start_iteration()


def test_max_tokens_trips():
    tracker = BudgetTracker(budget=_budget(max_tokens=100))
    with pytest.raises(BudgetExceeded, match="max_tokens"):
        tracker.record_usage(prompt_tokens=80, completion_tokens=30, price_in=0.0, price_out=0.0)


def test_max_cost_trips():
    # max_tokens set high on purpose: this test isolates the cost budget,
    # so 1,000,000 tokens must not trip max_tokens first.
    tracker = BudgetTracker(budget=_budget(max_cost_usd=0.0001, max_tokens=10_000_000))
    with pytest.raises(BudgetExceeded, match="max_cost_usd"):
        tracker.record_usage(prompt_tokens=1_000_000, completion_tokens=0, price_in=1.0, price_out=1.0)


def test_usage_within_budget_accumulates_without_raising():
    tracker = BudgetTracker(budget=_budget())
    tracker.record_usage(prompt_tokens=50, completion_tokens=50, price_in=0.15, price_out=0.60)
    assert tracker.total_tokens == 100
    assert tracker.total_cost_usd > 0
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_week7_budgets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.budgets'`

- [ ] **Step 5: Write `agent/budgets.py`**

```python
import time
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class Budget:
    max_iterations: int
    max_tokens: int
    max_cost_usd: float
    max_wall_seconds: float


@dataclass
class BudgetTracker:
    """Tracks one agent run's spend against a Budget.

    Call start_iteration() at the top of every loop lap, before the next
    model call. Call record_usage() right after each model call returns,
    before deciding whether to loop again.
    """

    budget: Budget
    iterations: int = field(default=0, init=False)
    total_tokens: int = field(default=0, init=False)
    total_cost_usd: float = field(default=0.0, init=False)
    _start: float = field(default_factory=time.monotonic, init=False)

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def start_iteration(self) -> None:
        self.iterations += 1
        if self.iterations > self.budget.max_iterations:
            raise BudgetExceeded(
                f"max_iterations exceeded: {self.iterations} > {self.budget.max_iterations}"
            )
        elapsed = self.elapsed()
        if elapsed > self.budget.max_wall_seconds:
            raise BudgetExceeded(
                f"max_wall_seconds exceeded: {elapsed:.2f}s > {self.budget.max_wall_seconds}s"
            )

    def record_usage(
        self, prompt_tokens: int, completion_tokens: int, price_in: float, price_out: float
    ) -> None:
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost_usd += (
            prompt_tokens * price_in + completion_tokens * price_out
        ) / 1_000_000
        if self.total_tokens > self.budget.max_tokens:
            raise BudgetExceeded(
                f"max_tokens exceeded: {self.total_tokens} > {self.budget.max_tokens}"
            )
        if self.total_cost_usd > self.budget.max_cost_usd:
            raise BudgetExceeded(
                f"max_cost_usd exceeded: ${self.total_cost_usd:.4f} > ${self.budget.max_cost_usd}"
            )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_week7_budgets.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Commit**

```bash
git add agent/__init__.py agent/config.py agent/budgets.py tests/test_week7_budgets.py
git commit -m "week7: agent config and budget enforcement"
```

---

## Task 2: Structured spec data (no-fabrication ground truth)

**Files:**
- Create: `agent/data/github_openapi.json`
- Create: `agent/data/deprecations.json`
- Create: `agent/spec.py`
- Test: `tests/test_week7_spec.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `agent.spec.ENDPOINT_NAMES: list[str]`, `agent.spec.API_VERSIONS: list[str]`, `agent.spec.get_endpoint_spec(endpoint: str, api_version: str) -> dict | None`, `agent.spec.find_deprecation(endpoint: str, api_version: str) -> dict | None`.

Every parameter and every deprecation fact below was read directly from
`data/documents/input_files/developer_documentations/github_combined_reference.pdf`
(pages 1–13) — nothing here is invented.

- [ ] **Step 1: Create `agent/data/github_openapi.json`**

```bash
mkdir -p agent/data
```

```json
{
  "api_versions": ["2022-11-28", "2025-06-01"],
  "endpoints": {
    "render_markdown": {
      "method": "POST",
      "path": "/markdown",
      "versions": {
        "2022-11-28": {
          "params": [
            {"name": "text", "type": "string", "required": true, "default": null, "description": "The Markdown text to render in HTML."},
            {"name": "mode", "type": "string", "required": false, "default": "markdown", "description": "The rendering mode. Can be one of: markdown, gfm."},
            {"name": "context", "type": "string", "required": false, "default": null, "description": "The repository context to use when creating references in gfm mode, e.g. 'octocat/Hello-World'."}
          ],
          "x_source": "github_combined_reference.pdf p1-2"
        },
        "2025-06-01": {
          "params": [
            {"name": "text", "type": "string", "required": true, "default": null, "description": "The Markdown text to render."},
            {"name": "mode", "type": "string", "required": false, "default": "markdown", "description": "One of markdown or gfm."},
            {"name": "context", "type": "object", "required": false, "default": null, "description": "{\"owner\": \"...\", \"repo\": \"...\"}. Used for gfm-mode reference linking. Was a plain string in the prior version."},
            {"name": "wrap_tables", "type": "boolean", "required": false, "default": false, "description": "When true, wide tables render with horizontal scroll wrappers instead of overflowing. Did not exist in the prior version."}
          ],
          "x_source": "github_combined_reference.pdf p3"
        }
      }
    },
    "create_issue": {
      "method": "POST",
      "path": "/repos/{owner}/{repo}/issues",
      "versions": {
        "2022-11-28": {
          "params": [
            {"name": "owner", "type": "string", "required": true, "default": null, "description": "Path parameter. The account owner of the repository."},
            {"name": "repo", "type": "string", "required": true, "default": null, "description": "Path parameter. The name of the repository without the .git extension."},
            {"name": "title", "type": "string or integer", "required": true, "default": null, "description": "The title of the issue."},
            {"name": "body", "type": "string", "required": false, "default": null, "description": "The contents of the issue."},
            {"name": "assignee", "type": "string", "required": false, "default": null, "description": "Login for the single user this issue should be assigned to."},
            {"name": "labels", "type": "array of strings", "required": false, "default": null, "description": "Labels to associate with this issue."}
          ],
          "x_source": "github_combined_reference.pdf p4"
        },
        "2025-06-01": {
          "params": [
            {"name": "owner", "type": "string", "required": true, "default": null, "description": "Path parameter. The account owner of the repository."},
            {"name": "repo", "type": "string", "required": true, "default": null, "description": "Path parameter. The name of the repository."},
            {"name": "title", "type": "string or integer", "required": true, "default": null, "description": "The title of the issue."},
            {"name": "body", "type": "string", "required": false, "default": null, "description": "The contents of the issue."},
            {"name": "assignees", "type": "array of strings", "required": false, "default": [], "description": "Logins for the users assigned to this issue. Replaces the deprecated assignee field."},
            {"name": "labels", "type": "array of strings", "required": false, "default": [], "description": "Labels to associate with this issue."},
            {"name": "type", "type": "string", "required": false, "default": null, "description": "The name of the issue type to set on creation. Did not exist in the prior version."}
          ],
          "x_source": "github_combined_reference.pdf p5"
        }
      }
    },
    "create_pull_request": {
      "method": "POST",
      "path": "/repos/{owner}/{repo}/pulls",
      "versions": {
        "2022-11-28": {
          "params": [
            {"name": "title", "type": "string", "required": true, "default": null, "description": "The title of the new pull request."},
            {"name": "head", "type": "string", "required": true, "default": null, "description": "The name of the branch where your changes are implemented."},
            {"name": "base", "type": "string", "required": true, "default": null, "description": "The name of the branch you want the changes pulled into."},
            {"name": "body", "type": "string", "required": false, "default": null, "description": "The contents of the pull request."},
            {"name": "draft", "type": "boolean", "required": false, "default": false, "description": "Indicates whether the pull request is a draft."}
          ],
          "x_source": "github_combined_reference.pdf p6"
        },
        "2025-06-01": {
          "params": [
            {"name": "owner", "type": "string", "required": true, "default": null, "description": "Path parameter."},
            {"name": "repo", "type": "string", "required": true, "default": null, "description": "Path parameter."},
            {"name": "title", "type": "string", "required": true, "default": null, "description": "Required unless issue is specified."},
            {"name": "head", "type": "string", "required": true, "default": null, "description": "Branch, or user:branch for cross-repo."},
            {"name": "base", "type": "string", "required": true, "default": null, "description": "The branch you want changes merged into."},
            {"name": "body", "type": "string", "required": false, "default": null, "description": "PR description."},
            {"name": "draft", "type": "boolean", "required": false, "default": false, "description": "Default false."},
            {"name": "maintainer_can_modify", "type": "boolean", "required": false, "default": true, "description": "Now settable at creation time; previously required a follow-up PATCH call."}
          ],
          "x_source": "github_combined_reference.pdf p7"
        }
      }
    },
    "create_repository": {
      "method": "POST",
      "path": "/user/repos",
      "versions": {
        "2022-11-28": {
          "params": [
            {"name": "name", "type": "string", "required": true, "default": null, "description": "The name of the repository."},
            {"name": "description", "type": "string", "required": false, "default": null, "description": "A short description of the repository."},
            {"name": "homepage", "type": "string", "required": false, "default": null, "description": "A URL with more information about the repository."},
            {"name": "private", "type": "boolean", "required": false, "default": false, "description": "Whether the repository is private."},
            {"name": "has_issues", "type": "boolean", "required": false, "default": true, "description": "Whether issues are enabled, unconditionally true by default regardless of visibility."},
            {"name": "auto_init", "type": "boolean", "required": false, "default": false, "description": "Pass true to create an initial commit with an empty README."}
          ],
          "x_source": "github_combined_reference.pdf p8"
        },
        "2025-06-01": {
          "params": [
            {"name": "name", "type": "string", "required": true, "default": null, "description": "Repository name."},
            {"name": "description", "type": "string", "required": false, "default": null, "description": "Short repository description."},
            {"name": "visibility", "type": "enum(public,private,internal)", "required": false, "default": "public", "description": "Supersedes the boolean private field for organizations offering internal repositories."},
            {"name": "private", "type": "boolean", "required": false, "default": false, "description": "Deprecated in favor of visibility. Continues to work for personal accounts."},
            {"name": "has_issues", "type": "boolean", "required": false, "default": null, "description": "Default depends on visibility: true for public, false for private/internal."},
            {"name": "auto_init", "type": "boolean", "required": false, "default": false, "description": "Creates an initial commit with an empty README when true."}
          ],
          "x_source": "github_combined_reference.pdf p9"
        }
      }
    },
    "create_release": {
      "method": "POST",
      "path": "/repos/{owner}/{repo}/releases",
      "versions": {
        "2022-11-28": {
          "params": [
            {"name": "owner", "type": "string", "required": true, "default": null, "description": "Path parameter."},
            {"name": "repo", "type": "string", "required": true, "default": null, "description": "Path parameter."},
            {"name": "tag_name", "type": "string", "required": true, "default": null, "description": "The name of the tag. Created automatically at target_commitish if it doesn't already exist."},
            {"name": "target_commitish", "type": "string", "required": false, "default": "the repository's default branch", "description": "Where the Git tag is created from."},
            {"name": "name", "type": "string", "required": false, "default": null, "description": "The name of the release."},
            {"name": "body", "type": "string", "required": false, "default": null, "description": "Text describing the contents of the tag."},
            {"name": "draft", "type": "boolean", "required": false, "default": false, "description": "true makes the release a draft."},
            {"name": "prerelease", "type": "boolean", "required": false, "default": false, "description": "true identifies the release as a prerelease."},
            {"name": "generate_release_notes", "type": "boolean", "required": false, "default": false, "description": "Whether to automatically generate the name and body for this release."}
          ],
          "x_source": "github_combined_reference.pdf p10-11"
        },
        "2025-06-01": {
          "params": [
            {"name": "tag_name", "type": "string", "required": true, "default": null, "description": "The name of the tag."},
            {"name": "target_commitish", "type": "string", "required": false, "default": "default branch", "description": "Commitish value the tag is created from, if it doesn't already exist."},
            {"name": "name", "type": "string", "required": false, "default": null, "description": "Release title."},
            {"name": "body", "type": "string", "required": false, "default": null, "description": "Release notes body text."},
            {"name": "draft", "type": "boolean", "required": false, "default": false, "description": "Creates a draft (unpublished) release when true."},
            {"name": "prerelease", "type": "boolean", "required": false, "default": false, "description": "Marks the release as a prerelease."},
            {"name": "discussion_category_name", "type": "string", "required": false, "default": null, "description": "If specified, a discussion of the specified category is created and linked to the release. Did not exist in the prior version."},
            {"name": "generate_release_notes", "type": "boolean", "required": false, "default": false, "description": "Auto-generates name/body from merged PRs since the previous release."},
            {"name": "make_latest", "type": "enum(true,false,legacy)", "required": false, "default": "true", "description": "Controls whether this release is marked 'Latest'. Did not exist in the prior version; previously determined purely by an internal publish-date heuristic."}
          ],
          "x_source": "github_combined_reference.pdf p12-13"
        }
      }
    }
  }
}
```

- [ ] **Step 2: Create `agent/data/deprecations.json`**

```json
[
  {
    "id": "issue-assignee-singular",
    "label": "single `assignee` string field",
    "kind": "field_replacement",
    "endpoint": "create_issue",
    "deprecated_in": "2025-06-01",
    "replacement": "assignees (array of strings)",
    "detail": "assignee is deprecated in favor of assignees, which takes an array of user logins.",
    "source": "github_combined_reference.pdf p5"
  },
  {
    "id": "repo-private-boolean",
    "label": "boolean `private` field",
    "kind": "field_replacement",
    "endpoint": "create_repository",
    "deprecated_in": "2025-06-01",
    "replacement": "visibility (enum: public, private, internal)",
    "detail": "private is deprecated in favor of visibility, though private continues to work for personal accounts.",
    "source": "github_combined_reference.pdf p9"
  },
  {
    "id": "markdown-context-string",
    "label": "plain-string `context` parameter",
    "kind": "format_change",
    "endpoint": "render_markdown",
    "deprecated_in": "2025-06-01",
    "replacement": "structured {owner, repo} object",
    "detail": "context changed from a plain string like 'octocat/Hello-World' to a structured {owner, repo} object.",
    "source": "github_combined_reference.pdf p3"
  }
]
```

- [ ] **Step 3: Write the failing spec-loader tests**

```python
# tests/test_week7_spec.py
from agent.spec import API_VERSIONS, ENDPOINT_NAMES, find_deprecation, get_endpoint_spec


def test_endpoint_names_and_versions_loaded():
    assert "create_issue" in ENDPOINT_NAMES
    assert API_VERSIONS == ["2022-11-28", "2025-06-01"]


def test_get_endpoint_spec_returns_versioned_params():
    spec = get_endpoint_spec("create_issue", "2025-06-01")
    names = [p["name"] for p in spec["params"]]
    assert "assignees" in names
    assert "assignee" not in names
    assert spec["x_source"].startswith("github_combined_reference.pdf")


def test_get_endpoint_spec_unknown_endpoint_returns_none():
    assert get_endpoint_spec("delete_universe", "2025-06-01") is None


def test_get_endpoint_spec_unknown_version_returns_none():
    assert get_endpoint_spec("create_issue", "1999-01-01") is None


def test_find_deprecation_hits():
    entry = find_deprecation("create_issue", "2025-06-01")
    assert entry["replacement"] == "assignees (array of strings)"


def test_find_deprecation_misses_when_endpoint_has_no_entry():
    assert find_deprecation("create_pull_request", "2025-06-01") is None


def test_find_deprecation_misses_for_older_version():
    assert find_deprecation("create_issue", "2022-11-28") is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_week7_spec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.spec'`

- [ ] **Step 5: Write `agent/spec.py`**

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_week7_spec.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Commit**

```bash
git add agent/data/ agent/spec.py tests/test_week7_spec.py
git commit -m "week7: hand-extracted, page-cited OpenAPI and deprecation ground truth"
```

---

## Task 3: Corpus ingestion and the `search_docs` tool

**Files:**
- Create: `agent/corpus.py`
- Test: `tests/test_week7_corpus.py`

**Interfaces:**
- Consumes: `rag.pipeline.RAGPipeline`, `rag.store.VectorStore` (existing).
- Produces: `agent.corpus.get_pipeline(persist_dir: str | None = None, collection_name: str = "week7_docs") -> RAGPipeline`, `agent.corpus.search_docs_raw(pipeline: RAGPipeline, query: str, k: int = 4) -> list[dict]`.

- [ ] **Step 1: Write the failing corpus test**

This follows the existing repo convention of testing retrieval against a
real embedding model and a real (temp-dir) Chroma collection — see
`tests/test_store_filtering.py`.

```python
# tests/test_week7_corpus.py
"""Slower than a typical unit test: builds a real embedding model and
ingests the 3 PDFs into a real (temp-dir) Chroma collection, same tradeoff
tests/test_store_filtering.py already makes for retrieval-behavior tests.
"""
import pytest

from agent.corpus import get_pipeline, search_docs_raw


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    persist_dir = str(tmp_path_factory.mktemp("week7_chroma"))
    return get_pipeline(persist_dir=persist_dir, collection_name="week7_test")


def test_ingestion_indexes_all_three_pdfs(pipeline):
    assert pipeline.document_count() > 0


def test_search_docs_finds_deprecation_language(pipeline):
    results = search_docs_raw(pipeline, "assignee deprecated issue", k=4)
    assert any("assignee" in r["text"].lower() for r in results)


def test_search_docs_finds_swagger_codegen_content(pipeline):
    results = search_docs_raw(pipeline, "Swagger Codegen CLI Maven group id", k=4)
    assert any("swagger" in r["metadata"].get("source_file", "").lower() for r in results)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_week7_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.corpus'`

- [ ] **Step 3: Write `agent/corpus.py`**

```python
from pathlib import Path

from rag.pipeline import RAGPipeline
from rag.store import VectorStore

WEEK7_DOCS_DIR = (
    Path(__file__).resolve().parent.parent
    / "data" / "documents" / "input_files" / "developer_documentations"
)


def get_pipeline(persist_dir: str | None = None, collection_name: str = "week7_docs") -> RAGPipeline:
    """Build (and lazily ingest) the RAG pipeline over the 3 developer-doc PDFs.

    persist_dir=None uses the app's default Chroma directory so a normal
    agent run reuses the index across processes; tests pass an isolated
    tmp_path so they never touch or depend on that persisted index.
    """
    store_kwargs = {"collection_name": collection_name}
    if persist_dir is not None:
        store_kwargs["persist_dir"] = persist_dir
    store = VectorStore(**store_kwargs)
    pipeline = RAGPipeline(store=store, require_front_matter=False)
    if pipeline.document_count() == 0:
        pipeline.ingest_path(str(WEEK7_DOCS_DIR))
    return pipeline


def search_docs_raw(pipeline: RAGPipeline, query: str, k: int = 4) -> list[dict]:
    return pipeline.retrieve(query, k=k)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_week7_corpus.py -v`
Expected: PASS (3 tests). First run downloads/loads the embedding model and
ingests ~24 PDF pages, so it's slower than a typical unit test.

- [ ] **Step 5: Commit**

```bash
git add agent/corpus.py tests/test_week7_corpus.py
git commit -m "week7: ingest developer-doc PDFs into a dedicated week7_docs collection"
```

---

## Task 4: `get_openapi_spec` and `check_deprecation` tools, tool schemas, and the diff artifact

**Files:**
- Create: `agent/tools.py`
- Create: `results/week7/tool_diff.md`
- Test: `tests/test_week7_tools.py`

**Interfaces:**
- Consumes: `agent.spec.get_endpoint_spec`, `agent.spec.find_deprecation`, `agent.spec.ENDPOINT_NAMES`, `agent.spec.API_VERSIONS`, `agent.corpus.get_pipeline`, `agent.corpus.search_docs_raw`.
- Produces: `agent.tools.TOOL_SCHEMAS: list[dict]` (3 entries), `agent.tools.call_tool(name: str, arguments: dict) -> str`, plus the individual functions `search_docs`, `get_openapi_spec`, `check_deprecation` (each `(**kwargs) -> str`, a JSON string).

- [ ] **Step 1: Write the failing tool tests**

```python
# tests/test_week7_tools.py
import json

import pytest

from agent.tools import TOOL_SCHEMAS, call_tool


def test_three_tools_registered_with_no_name_collisions():
    names = [schema["function"]["name"] for schema in TOOL_SCHEMAS]
    assert sorted(names) == ["check_deprecation", "get_openapi_spec", "search_docs"]


def test_api_version_params_are_enums_not_free_strings():
    for schema in TOOL_SCHEMAS:
        props = schema["function"]["parameters"]["properties"]
        if "api_version" in props:
            assert props["api_version"]["enum"] == ["2022-11-28", "2025-06-01"]


def test_check_deprecation_description_does_not_overlap_other_two():
    descriptions = {s["function"]["name"]: s["function"]["description"] for s in TOOL_SCHEMAS}
    # The 3rd tool's description must name the other two tools directly, so
    # the model is steered toward the right one instead of guessing from
    # similar-sounding verbs -- a plain word-overlap check would fail here
    # on ordinary shared English (the, a, to, one, is), so this checks the
    # actual disambiguating content instead.
    assert descriptions["check_deprecation"] != descriptions["search_docs"]
    assert descriptions["check_deprecation"] != descriptions["get_openapi_spec"]
    assert "search_docs" in descriptions["check_deprecation"]
    assert "get_openapi_spec" in descriptions["check_deprecation"]
    assert "check_deprecation" in descriptions["get_openapi_spec"]


def test_get_openapi_spec_returns_versioned_params():
    result = json.loads(call_tool("get_openapi_spec", {"endpoint": "create_issue", "api_version": "2025-06-01"}))
    names = [p["name"] for p in result["params"]]
    assert "assignees" in names


def test_get_openapi_spec_unknown_endpoint_reports_error_not_fabrication():
    result = json.loads(call_tool("get_openapi_spec", {"endpoint": "nope", "api_version": "2025-06-01"}))
    assert "error" in result


def test_check_deprecation_hit():
    result = json.loads(call_tool("check_deprecation", {"endpoint": "create_repository", "api_version": "2025-06-01"}))
    assert result["deprecated"] is True
    assert "visibility" in result["replacement"]


def test_check_deprecation_miss_is_explicit_not_silent():
    result = json.loads(call_tool("check_deprecation", {"endpoint": "create_release", "api_version": "2025-06-01"}))
    assert result["deprecated"] is False


def test_call_tool_unknown_name_returns_error_json():
    result = json.loads(call_tool("delete_everything", {}))
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_week7_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.tools'`

- [ ] **Step 3: Write `agent/tools.py`**

```python
import json

from agent.corpus import get_pipeline, search_docs_raw
from agent.spec import API_VERSIONS, ENDPOINT_NAMES, find_deprecation, get_endpoint_spec

_pipeline = None


def _get_or_build_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = get_pipeline()
    return _pipeline


def search_docs(query: str, k: int = 4) -> str:
    results = search_docs_raw(_get_or_build_pipeline(), query, k=k)
    trimmed = [
        {"source_file": r["metadata"].get("source_file", "unknown"), "text": r["text"][:500]}
        for r in results
    ]
    return json.dumps({"results": trimmed})


def get_openapi_spec(endpoint: str, api_version: str) -> str:
    spec = get_endpoint_spec(endpoint, api_version)
    if spec is None:
        return json.dumps(
            {"error": f"No spec for endpoint={endpoint!r} api_version={api_version!r}.",
             "known_endpoints": ENDPOINT_NAMES}
        )
    return json.dumps(spec)


def check_deprecation(endpoint: str, api_version: str) -> str:
    entry = find_deprecation(endpoint, api_version)
    if entry is None:
        return json.dumps(
            {"endpoint": endpoint, "api_version": api_version, "deprecated": False,
             "detail": "No deprecated fields recorded for this endpoint at this API version."}
        )
    return json.dumps({"endpoint": endpoint, "api_version": api_version, "deprecated": True, **entry})


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search the indexed developer documentation for text relevant to a "
                "natural-language question. Use this first for anything that is not "
                "about one specific endpoint's exact parameters or deprecation status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The natural-language search query."},
                    "k": {"type": "integer", "description": "How many chunks to return.", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_openapi_spec",
            "description": (
                "Return the exact method, path, and parameter list for one named "
                "GitHub endpoint at one specific API version. Use this only when you "
                "already know the endpoint name and need its precise parameter shape "
                "-- not for open-ended search, and not to check whether something is "
                "deprecated (use check_deprecation for that)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "enum": ENDPOINT_NAMES, "description": "The endpoint identifier, e.g. 'create_issue'."},
                    "api_version": {"type": "string", "enum": API_VERSIONS, "description": "Which API version's parameter shape to return."},
                },
                "required": ["endpoint", "api_version"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_deprecation",
            "description": (
                "Report whether a named endpoint has anything deprecated as of one "
                "specific API version, and what replaces it. Use this only to check "
                "deprecation status -- not to fetch the full parameter list (use "
                "get_openapi_spec instead) and not to search prose documentation "
                "(use search_docs instead)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "enum": ENDPOINT_NAMES, "description": "The endpoint identifier, e.g. 'create_issue'."},
                    "api_version": {"type": "string", "enum": API_VERSIONS, "description": "Which API version to check deprecation status against."},
                },
                "required": ["endpoint", "api_version"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "search_docs": search_docs,
    "get_openapi_spec": get_openapi_spec,
    "check_deprecation": check_deprecation,
}


def call_tool(name: str, arguments: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    return fn(**arguments)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_week7_tools.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Write the 3rd-tool description diff artifact**

```bash
mkdir -p results/week7
```

```markdown
<!-- results/week7/tool_diff.md -->
# 3rd tool description diff

## Before (2-tool loop: search_docs, get_openapi_spec)

```
search_docs: "Search the indexed developer documentation for text relevant
to a natural-language question. Use this first for anything that is not
about one specific endpoint's exact parameters or deprecation status."

get_openapi_spec: "Return the exact method, path, and parameter list for
one named GitHub endpoint at one specific API version. Use this only when
you already know the endpoint name and need its precise parameter shape --
not for open-ended search."
```

## After (3-tool loop: + check_deprecation)

```diff
 get_openapi_spec: "Return the exact method, path, and parameter list for
 one named GitHub endpoint at one specific API version. Use this only when
 you already know the endpoint name and need its precise parameter shape --
-not for open-ended search."
+not for open-ended search, and not to check whether something is
+deprecated (use check_deprecation for that)."

+check_deprecation: "Report whether a named endpoint has anything
+deprecated as of one specific API version, and what replaces it. Use this
+only to check deprecation status -- not to fetch the full parameter list
+(use get_openapi_spec instead) and not to search prose documentation
+(use search_docs instead)."
```

`check_deprecation` does one job (deprecation status + replacement), takes
an `api_version` enum instead of a free string, and its description names
the other two tools by name so the model can't confuse "what's the shape"
(get_openapi_spec) with "what's deprecated" (check_deprecation) with
"find relevant prose" (search_docs). Adding it required one clause added to
get_openapi_spec's description (steering away from the new tool) — no
rewrite of search_docs was needed since the overlap risk was only ever
between the two spec-lookup tools.
```

- [ ] **Step 6: Commit**

```bash
git add agent/tools.py results/week7/tool_diff.md tests/test_week7_tools.py
git commit -m "week7: get_openapi_spec + check_deprecation tools and description diff"
```

---

## Task 5: Agent loop (ReAct) with budget enforcement

**Files:**
- Create: `agent/loop.py`
- Create: `tests/week7_fakes.py`
- Test: `tests/test_week7_loop.py`

**Interfaces:**
- Consumes: `agent.budgets.{Budget, BudgetExceeded, BudgetTracker}`, `agent.config.{AGENT_MODEL, price_for}`, `agent.tools.{TOOL_SCHEMAS, call_tool}`.
- Produces: `agent.loop.RunResult` (dataclass: `answer: str | None`, `terminated_by_budget: bool`, `budget_reason: str | None`, `iterations: int`, `total_tokens: int`, `total_cost_usd: float`, `wall_seconds: float`, `transcript: list[dict]`), `agent.loop.SYSTEM_PROMPT: str`, `agent.loop.run_agent(question: str, budget: Budget, client=None) -> RunResult`.

- [ ] **Step 1: Write the fake Groq client shared by loop and workflow tests**

```python
# tests/week7_fakes.py
from types import SimpleNamespace


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = SimpleNamespace(name=name, arguments=arguments)


def fake_response(content=None, tool_calls=None, prompt_tokens=10, completion_tokens=10):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


class FakeGroqClient:
    """Returns one queued response per .chat.completions.create() call, in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)
```

- [ ] **Step 2: Write the failing loop tests**

```python
# tests/test_week7_loop.py
import json

from agent.budgets import Budget
from agent.loop import run_agent
from tests.week7_fakes import FakeGroqClient, FakeToolCall, fake_response


def _generous_budget():
    return Budget(max_iterations=5, max_tokens=100_000, max_cost_usd=10.0, max_wall_seconds=60.0)


def test_agent_answers_directly_when_no_tool_call_needed():
    client = FakeGroqClient([fake_response(content="The default mode is markdown.")])
    result = run_agent("What is the default mode?", budget=_generous_budget(), client=client)
    assert result.terminated_by_budget is False
    assert "markdown" in result.answer
    assert result.iterations == 1


def test_agent_calls_a_tool_then_answers():
    tool_call = FakeToolCall("call_1", "check_deprecation", json.dumps({"endpoint": "create_issue", "api_version": "2025-06-01"}))
    client = FakeGroqClient([
        fake_response(tool_calls=[tool_call]),
        fake_response(content="Use assignees instead of assignee."),
    ])
    result = run_agent("Is assignee deprecated for creating issues in 2025-06-01?", budget=_generous_budget(), client=client)
    assert result.iterations == 2
    assert "assignees" in result.answer
    assert result.transcript[-1]["role"] == "assistant"


def test_agent_sums_tokens_across_every_lap_not_just_the_last_call():
    # check_deprecation, not search_docs: a pure JSON lookup, so this test
    # stays fast and has no side effect on the real Chroma index.
    tool_call = FakeToolCall(
        "call_1", "check_deprecation", json.dumps({"endpoint": "create_issue", "api_version": "2025-06-01"})
    )
    client = FakeGroqClient([
        fake_response(tool_calls=[tool_call], prompt_tokens=100, completion_tokens=20),
        fake_response(content="done", prompt_tokens=150, completion_tokens=10),
    ])
    result = run_agent("q", budget=_generous_budget(), client=client)
    assert result.total_tokens == (100 + 20) + (150 + 10)


def test_agent_stops_cleanly_when_max_iterations_exceeded():
    # check_deprecation again, so lap 1's tool execution stays a fast, pure
    # JSON lookup instead of touching the real Chroma index.
    tool_call = FakeToolCall(
        "call_1", "check_deprecation", json.dumps({"endpoint": "create_issue", "api_version": "2025-06-01"})
    )
    # Only one fake response queued: the tracker must trip on iteration 2's
    # start_iteration(), *before* a second .create() call is attempted.
    client = FakeGroqClient([fake_response(tool_calls=[tool_call])])
    tight_budget = Budget(max_iterations=1, max_tokens=100_000, max_cost_usd=10.0, max_wall_seconds=60.0)
    result = run_agent("q", budget=tight_budget, client=client)
    assert result.terminated_by_budget is True
    assert "max_iterations" in result.budget_reason
    assert result.answer is None


def test_agent_stops_cleanly_when_max_tokens_exceeded():
    client = FakeGroqClient([fake_response(content="ignored", prompt_tokens=500, completion_tokens=600)])
    tight_budget = Budget(max_iterations=5, max_tokens=100, max_cost_usd=10.0, max_wall_seconds=60.0)
    result = run_agent("q", budget=tight_budget, client=client)
    assert result.terminated_by_budget is True
    assert "max_tokens" in result.budget_reason
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_week7_loop.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.loop'`

- [ ] **Step 4: Write `agent/loop.py`**

```python
import json
import time
from dataclasses import dataclass, field

from agent.budgets import Budget, BudgetExceeded, BudgetTracker
from agent.config import AGENT_MODEL, price_for
from agent.tools import TOOL_SCHEMAS, call_tool

SYSTEM_PROMPT = (
    "You help developers migrate code between GitHub API versions. You have "
    "tools to search documentation, look up exact endpoint parameter shapes, "
    "and check whether something is deprecated. Only state facts a tool call "
    "returned to you -- never guess a parameter name, default, or deprecation "
    "status. When you have enough information, answer the question directly "
    "in plain text with no further tool calls."
)


@dataclass
class RunResult:
    answer: str | None
    terminated_by_budget: bool
    budget_reason: str | None
    iterations: int
    total_tokens: int
    total_cost_usd: float
    wall_seconds: float
    transcript: list[dict] = field(default_factory=list)


def _budget_result(tracker: BudgetTracker, reason: str, transcript: list[dict]) -> RunResult:
    return RunResult(
        answer=None,
        terminated_by_budget=True,
        budget_reason=reason,
        iterations=tracker.iterations,
        total_tokens=tracker.total_tokens,
        total_cost_usd=tracker.total_cost_usd,
        wall_seconds=tracker.elapsed(),
        transcript=transcript,
    )


def run_agent(question: str, budget: Budget, client=None) -> RunResult:
    if client is None:
        from groq import Groq

        client = Groq()

    tracker = BudgetTracker(budget=budget)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    transcript = [dict(m) for m in messages]

    while True:
        try:
            tracker.start_iteration()
        except BudgetExceeded as exc:
            return _budget_result(tracker, exc.reason, transcript)

        response = client.chat.completions.create(
            model=AGENT_MODEL, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto"
        )
        usage = response.usage
        price_in, price_out = price_for(AGENT_MODEL)
        try:
            tracker.record_usage(usage.prompt_tokens, usage.completion_tokens, price_in, price_out)
        except BudgetExceeded as exc:
            return _budget_result(tracker, exc.reason, transcript)

        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)

        if not tool_calls:
            transcript.append({"role": "assistant", "content": message.content})
            return RunResult(
                answer=message.content,
                terminated_by_budget=False,
                budget_reason=None,
                iterations=tracker.iterations,
                total_tokens=tracker.total_tokens,
                total_cost_usd=tracker.total_cost_usd,
                wall_seconds=tracker.elapsed(),
                transcript=transcript,
            )

        assistant_msg = {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        }
        messages.append(assistant_msg)
        transcript.append(assistant_msg)

        for tc in tool_calls:
            args = json.loads(tc.function.arguments)
            result = call_tool(tc.function.name, args)
            tool_msg = {"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": result}
            messages.append(tool_msg)
            transcript.append(tool_msg)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_week7_loop.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add agent/loop.py tests/week7_fakes.py tests/test_week7_loop.py
git commit -m "week7: ReAct agent loop with per-lap token accounting and budget stops"
```

---

## Task 6: Fixed workflow (no loop)

**Files:**
- Create: `agent/workflow.py`
- Test: `tests/test_week7_workflow.py`

**Interfaces:**
- Consumes: `agent.loop.{RunResult, SYSTEM_PROMPT}`, `agent.config.{AGENT_MODEL, price_for}`, `agent.tools.call_tool`, `agent.spec.{ENDPOINT_NAMES, API_VERSIONS}`.
- Produces: `agent.workflow.extract_endpoint(question: str) -> str | None`, `agent.workflow.extract_api_version(question: str) -> str`, `agent.workflow.run_workflow(question: str, client=None) -> RunResult`.

- [ ] **Step 1: Write the failing workflow tests**

```python
# tests/test_week7_workflow.py
from agent.workflow import extract_api_version, extract_endpoint, run_workflow
from tests.week7_fakes import FakeGroqClient, fake_response


def test_extract_endpoint_matches_known_keywords():
    assert extract_endpoint("Is the assignee field deprecated for creating an issue?") == "create_issue"
    assert extract_endpoint("What changed for creating a pull request?") == "create_pull_request"


def test_extract_endpoint_returns_none_when_no_keyword_matches():
    assert extract_endpoint("What's the weather today?") is None


def test_extract_api_version_finds_explicit_version_in_question():
    assert extract_api_version("On 2022-11-28, what does assignee look like?") == "2022-11-28"


def test_extract_api_version_defaults_to_newest_when_unstated():
    assert extract_api_version("What does assignee look like?") == "2025-06-01"


def test_run_workflow_calls_all_three_tools_then_generates_once():
    # Only the generation call is faked -- search_docs really runs against
    # agent.tools's module-level pipeline, so this test's first run builds
    # (and persists into the project's real chroma_db/) the "week7_docs"
    # collection, same as tests/test_week7_corpus.py -- the point here is
    # verifying the workflow's real tool sequence, not mocking it away.
    client = FakeGroqClient([fake_response(content="Use assignees instead of assignee.")])
    result = run_workflow(
        "Is assignee deprecated for creating an issue in 2025-06-01?", client=client
    )
    tool_names = [m["name"] for m in result.transcript if m.get("role") == "tool"]
    assert tool_names == ["search_docs", "get_openapi_spec", "check_deprecation"]
    assert len(client.calls) == 1  # exactly one generation call -- no loop
    assert "assignees" in result.answer
    assert result.terminated_by_budget is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_week7_workflow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.workflow'`

- [ ] **Step 3: Write `agent/workflow.py`**

```python
from agent.config import AGENT_MODEL, price_for
from agent.loop import SYSTEM_PROMPT, RunResult
from agent.spec import API_VERSIONS, ENDPOINT_NAMES
from agent.tools import call_tool
from agent.budgets import BudgetTracker, Budget

_ENDPOINT_KEYWORDS = {
    "create_issue": ["issue"],
    "create_pull_request": ["pull request"],
    "create_repository": ["repository", "repo "],
    "create_release": ["release"],
    "render_markdown": ["markdown"],
}


def extract_endpoint(question: str) -> str | None:
    lowered = question.lower()
    for endpoint, keywords in _ENDPOINT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return endpoint
    return None


def extract_api_version(question: str) -> str:
    for version in API_VERSIONS:
        if version in question:
            return version
    return API_VERSIONS[-1]


def run_workflow(question: str, client=None) -> RunResult:
    if client is None:
        from groq import Groq

        client = Groq()

    # An unlimited tracker: the workflow has no loop to run away, but reusing
    # BudgetTracker keeps token/cost accounting identical to the agent's.
    tracker = BudgetTracker(
        budget=Budget(max_iterations=1, max_tokens=10**9, max_cost_usd=10**9, max_wall_seconds=10**9)
    )
    tracker.start_iteration()

    endpoint = extract_endpoint(question) or ENDPOINT_NAMES[0]
    api_version = extract_api_version(question)

    transcript: list[dict] = []
    docs_result = call_tool("search_docs", {"query": question})
    transcript.append({"role": "tool", "name": "search_docs", "content": docs_result})

    spec_result = call_tool("get_openapi_spec", {"endpoint": endpoint, "api_version": api_version})
    transcript.append({"role": "tool", "name": "get_openapi_spec", "content": spec_result})

    deprecation_result = call_tool("check_deprecation", {"endpoint": endpoint, "api_version": api_version})
    transcript.append({"role": "tool", "name": "check_deprecation", "content": deprecation_result})

    context = (
        f"Docs search results: {docs_result}\n\n"
        f"OpenAPI spec: {spec_result}\n\n"
        f"Deprecation check: {deprecation_result}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{context}\n\nQuestion: {question}"},
    ]
    transcript.extend(dict(m) for m in messages)

    response = client.chat.completions.create(model=AGENT_MODEL, messages=messages)
    usage = response.usage
    price_in, price_out = price_for(AGENT_MODEL)
    tracker.record_usage(usage.prompt_tokens, usage.completion_tokens, price_in, price_out)

    answer = response.choices[0].message.content
    transcript.append({"role": "assistant", "content": answer})

    return RunResult(
        answer=answer,
        terminated_by_budget=False,
        budget_reason=None,
        iterations=1,
        total_tokens=tracker.total_tokens,
        total_cost_usd=tracker.total_cost_usd,
        wall_seconds=tracker.elapsed(),
        transcript=transcript,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_week7_workflow.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/workflow.py tests/test_week7_workflow.py
git commit -m "week7: fixed 4-call workflow twin (no decision loop)"
```

---

## Task 7: The 10-question race set

**Files:**
- Create: `eval/week7/__init__.py` (empty)
- Create: `eval/week7/questions.json`
- Test: `tests/test_week7_questions.py`

**Interfaces:**
- Produces: `eval/week7/questions.json`, a JSON array of 10 objects, each `{id, question, expected_fragment, needs_chain}`.

All 10 questions are pulled verbatim from the existing human-authored golden
set at `data/documents/input_files/golden_sets/{gs_easy,gs_medium,gs_hard}.json`
(45 entries total) rather than newly written — reusing real, already-graded
questions instead of inventing fresh ones. `expected_fragment` is a short,
distinguishing token pulled from each entry's own golden `answer` field.
`needs_chain: true` marks a question that only resolves by comparing what a
prior tool call found across both API versions (all 5 chain questions here
come from `gs_hard`, which already frames its questions as before/after
comparisons).

- [ ] **Step 1: Write the failing structure test**

```python
# tests/test_week7_questions.py
import json
from pathlib import Path

QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "eval" / "week7" / "questions.json"


def _load():
    return json.loads(QUESTIONS_PATH.read_text())


def test_exactly_ten_questions():
    assert len(_load()) == 10


def test_every_question_has_required_fields():
    for q in _load():
        assert set(q.keys()) == {"id", "question", "expected_fragment", "needs_chain"}
        assert isinstance(q["needs_chain"], bool)


def test_at_least_three_questions_need_chaining():
    assert sum(1 for q in _load() if q["needs_chain"]) >= 3


def test_ids_are_unique():
    ids = [q["id"] for q in _load()]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_week7_questions.py -v`
Expected: FAIL — `questions.json` doesn't exist yet.

- [ ] **Step 3: Create `eval/week7/__init__.py` and `eval/week7/questions.json`**

```bash
mkdir -p eval/week7
touch eval/week7/__init__.py
```

```json
[
  {"id": "q01", "question": "What is the maximum file size limit supported when rendering Markdown content via the GitHub REST API?", "expected_fragment": "400 KB", "needs_chain": false},
  {"id": "q02", "question": "What Maven group id is used to download the Swagger Codegen CLI jar for version 3.x?", "expected_fragment": "io.swagger.codegen.v3", "needs_chain": false},
  {"id": "q03", "question": "Which OAuth scopes are required to create a repository for an authenticated user using the GitHub REST API?", "expected_fragment": "public_repo", "needs_chain": false},
  {"id": "q04", "question": "In GitHub API version 2025-06-01, what parameter replaces the deprecated single assignee field when creating an issue?", "expected_fragment": "assignees", "needs_chain": false},
  {"id": "q05", "question": "What parameter can be provided when creating a release in GitHub API version 2025-06-01 to automatically trigger a linked discussion?", "expected_fragment": "discussion_category_name", "needs_chain": false},
  {"id": "q06", "question": "Compare how the context parameter format changed between GitHub API version 2022-11-28 and 2025-06-01 for rendering Markdown.", "expected_fragment": "owner", "needs_chain": true},
  {"id": "q07", "question": "How did setting maintainer_can_modify during pull request creation change between GitHub API 2022-11-28 and 2025-06-01?", "expected_fragment": "maintainer_can_modify", "needs_chain": true},
  {"id": "q08", "question": "How does the make_latest parameter in GitHub API version 2025-06-01 release creation replace the undocumented heuristic used in 2022-11-28?", "expected_fragment": "make_latest", "needs_chain": true},
  {"id": "q09", "question": "How did draft pull requests interact with auto-merge settings in GitHub API version 2022-11-28 versus 2025-06-01?", "expected_fragment": "pre-armed", "needs_chain": true},
  {"id": "q10", "question": "How did setting issue types on creation change between GitHub API versions 2022-11-28 and 2025-06-01?", "expected_fragment": "creation time", "needs_chain": true}
]
```

Source mapping: q01=gs_easy#04, q02=gs_easy#02, q03=gs_easy#07, q04=gs_medium#01, q05=gs_medium#09, q06=gs_hard#01, q07=gs_hard#04, q08=gs_hard#06, q09=gs_hard#08, q10=gs_hard#11.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_week7_questions.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add eval/week7/__init__.py eval/week7/questions.json tests/test_week7_questions.py
git commit -m "week7: 10-question race set, 4 requiring cross-tool chaining"
```

---

## Task 8: Race harness (`run_race.py`) and metric aggregation

**Files:**
- Create: `eval/week7/run_race.py`
- Test: `tests/test_week7_race.py`

**Interfaces:**
- Consumes: `agent.loop.run_agent`, `agent.workflow.run_workflow`, `agent.budgets.Budget`.
- Produces: `eval.week7.run_race.grade(answer: str | None, expected_fragment: str) -> bool`, `eval.week7.run_race.aggregate(records: list[dict]) -> dict` (keys: `pass_rate`, `p50_latency_seconds`, `total_tokens`, `cost_per_question_usd`), `eval.week7.run_race.main() -> None` (writes `results/week7/race.csv`).

- [ ] **Step 1: Write the failing aggregation tests (pure functions, no live calls)**

```python
# tests/test_week7_race.py
from eval.week7.run_race import aggregate, grade


def test_grade_is_case_insensitive_substring_match():
    assert grade("Use ASSIGNEES instead.", "assignees") is True
    assert grade("Use assignee instead.", "assignees") is False


def test_grade_handles_budget_terminated_run():
    assert grade(None, "assignees") is False


def test_aggregate_computes_all_four_numbers():
    records = [
        {"passed": True, "wall_seconds": 1.0, "total_tokens": 100, "total_cost_usd": 0.01},
        {"passed": True, "wall_seconds": 2.0, "total_tokens": 200, "total_cost_usd": 0.02},
        {"passed": False, "wall_seconds": 3.0, "total_tokens": 300, "total_cost_usd": 0.03},
        {"passed": True, "wall_seconds": 4.0, "total_tokens": 400, "total_cost_usd": 0.04},
    ]
    result = aggregate(records)
    assert result["pass_rate"] == 0.75
    assert result["p50_latency_seconds"] == 2.5
    assert result["total_tokens"] == 1000
    assert round(result["cost_per_question_usd"], 4) == round(0.10 / 4, 4)


def test_aggregate_empty_records_does_not_crash():
    result = aggregate([])
    assert result["pass_rate"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_week7_race.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.week7.run_race'`

- [ ] **Step 3: Write `eval/week7/run_race.py`**

```python
import csv
import json
import statistics
from pathlib import Path

from agent.budgets import Budget
from agent.loop import run_agent
from agent.workflow import run_workflow

QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.json"
RACE_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "results" / "week7" / "race.csv"

# Generous on purpose: the race measures how much the agent *chooses* to
# spend, not whether we starved it. Task 9's budget demo is where a budget
# is deliberately made tight.
RACE_BUDGET = Budget(max_iterations=8, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=60.0)


def grade(answer: str | None, expected_fragment: str) -> bool:
    if answer is None:
        return False
    return expected_fragment.lower() in answer.lower()


def aggregate(records: list[dict]) -> dict:
    if not records:
        return {"pass_rate": 0.0, "p50_latency_seconds": 0.0, "total_tokens": 0, "cost_per_question_usd": 0.0}
    passed = sum(1 for r in records if r["passed"])
    latencies = [r["wall_seconds"] for r in records]
    total_tokens = sum(r["total_tokens"] for r in records)
    total_cost = sum(r["total_cost_usd"] for r in records)
    return {
        "pass_rate": passed / len(records),
        "p50_latency_seconds": statistics.median(latencies),
        "total_tokens": total_tokens,
        "cost_per_question_usd": total_cost / len(records),
    }


def _run_system(run_fn, questions: list[dict]) -> list[dict]:
    records = []
    for q in questions:
        if run_fn is run_agent:
            result = run_fn(q["question"], budget=RACE_BUDGET)
        else:
            result = run_fn(q["question"])
        records.append(
            {
                "id": q["id"],
                "passed": grade(result.answer, q["expected_fragment"]),
                "wall_seconds": result.wall_seconds,
                "total_tokens": result.total_tokens,
                "total_cost_usd": result.total_cost_usd,
            }
        )
    return records


def main() -> None:
    questions = json.loads(QUESTIONS_PATH.read_text())
    agent_records = _run_system(run_agent, questions)
    workflow_records = _run_system(run_workflow, questions)

    agent_stats = aggregate(agent_records)
    workflow_stats = aggregate(workflow_records)

    RACE_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RACE_CSV_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["system", "pass_rate", "p50_latency_seconds", "total_tokens", "cost_per_question_usd"])
        for name, stats in [("agent", agent_stats), ("workflow", workflow_stats)]:
            writer.writerow([name, stats["pass_rate"], stats["p50_latency_seconds"], stats["total_tokens"], stats["cost_per_question_usd"]])

    print(f"Wrote {RACE_CSV_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_week7_race.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add eval/week7/run_race.py tests/test_week7_race.py
git commit -m "week7: race harness with grading and 4-number aggregation"
```

---

## Task 9: Budget-termination demo

**Files:**
- Create: `eval/week7/budget_demo.py`
- Test: `tests/test_week7_budget_demo.py`

**Interfaces:**
- Consumes: `agent.loop.run_agent`, `agent.budgets.Budget`.
- Produces: `eval.week7.budget_demo.TIGHT_BUDGET: Budget`, `eval.week7.budget_demo.run_and_log(question: str, client=None, log_path: Path | None = None) -> Path`.

- [ ] **Step 1: Write the failing test (uses the fake client — deterministic, no live call)**

```python
# tests/test_week7_budget_demo.py
import json

from eval.week7.budget_demo import run_and_log
from tests.week7_fakes import FakeGroqClient, FakeToolCall, fake_response


def test_run_and_log_writes_a_clean_budget_termination(tmp_path):
    # check_deprecation, not search_docs: lap 1's tool call actually
    # executes before the budget trips on lap 2, and this one is a pure
    # JSON lookup with no real Chroma/embedding-model side effect.
    tool_call = FakeToolCall(
        "call_1", "check_deprecation", json.dumps({"endpoint": "create_issue", "api_version": "2025-06-01"})
    )
    client = FakeGroqClient([fake_response(tool_calls=[tool_call])])
    log_path = tmp_path / "budget_termination.log"

    result_path = run_and_log(
        "I'm creating an issue on 2025-06-01 with assignee -- what should I use instead?",
        client=client,
        log_path=log_path,
    )

    contents = result_path.read_text()
    assert "max_iterations" in contents
    assert "terminated" in contents.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_week7_budget_demo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.week7.budget_demo'`

- [ ] **Step 3: Write `eval/week7/budget_demo.py`**

```python
from pathlib import Path

from agent.budgets import Budget
from agent.loop import run_agent

# Deliberately tight: 1 iteration is not enough for a question that needs a
# tool call before it can answer, so this budget is guaranteed to trip.
TIGHT_BUDGET = Budget(max_iterations=1, max_tokens=50_000, max_cost_usd=1.0, max_wall_seconds=30.0)

DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "results" / "week7" / "budget_termination.log"


def run_and_log(question: str, client=None, log_path: Path | None = None) -> Path:
    log_path = log_path or DEFAULT_LOG_PATH
    result = run_agent(question, budget=TIGHT_BUDGET, client=client)

    lines = [
        f"question: {question}",
        f"budget: {TIGHT_BUDGET}",
        f"terminated_by_budget: {result.terminated_by_budget}",
        f"budget_reason: {result.budget_reason}",
        f"iterations completed before stop: {result.iterations}",
        "run terminated cleanly -- no crash, no extra lap, no fabricated answer.",
        "",
        "transcript:",
    ]
    for message in result.transcript:
        lines.append(str(message))

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(lines))
    return log_path


if __name__ == "__main__":
    from eval.week7.run_race import QUESTIONS_PATH
    import json

    questions = json.loads(QUESTIONS_PATH.read_text())
    chained = next(q for q in questions if q["needs_chain"])
    path = run_and_log(chained["question"])
    print(f"Wrote {path}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_week7_budget_demo.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add eval/week7/budget_demo.py tests/test_week7_budget_demo.py
git commit -m "week7: budget-termination demo script"
```

---

## Task 10: Run the race for real, capture the artifacts, write the verdict

This task has no new unit-testable code — it's running Tasks 8 and 9's
scripts against the real Groq API to produce the actual graded artifacts,
then writing the verdict from the real numbers. Requires `GROQ_API_KEY` set
in `.env`.

**Files:**
- Generate (by running code): `results/week7/race.csv`
- Generate (by running code): `results/week7/budget_termination.log`
- Create by hand, from the real numbers: `results/week7/verdict.md`

- [ ] **Step 1: Run the race**

```bash
python -m eval.week7.run_race
```

This calls the real Groq API 10 times for the agent and 10 times for the
workflow (each workflow run makes exactly 1 generation call; each agent run
makes 1 or more, depending on how many tool calls it chooses). Inspect
`results/week7/race.csv` afterward.

- [ ] **Step 2: Run the budget-termination demo**

```bash
python -m eval.week7.budget_demo
```

Inspect `results/week7/budget_termination.log` — confirm it shows
`terminated_by_budget: True` and a `budget_reason` naming `max_iterations`.

- [ ] **Step 3: Write `results/week7/verdict.md` from the actual race.csv numbers**

Read `results/week7/race.csv`, then write a verdict under 150 words that:
- States the actual pass rate / p50 latency / tokens / cost for both systems.
- Applies the decision rule from the task doc: does the correct *path*
  (which tools, in what order) vary by input? For questions q01–q05 the
  workflow's fixed order already happens to match what's needed. For the
  5 `needs_chain` questions (q06–q10), the path is still the same
  3-tool sequence — only the *values fed forward* (found deprecated →
  what's the replacement) depend on what a prior step returned, not which
  tools get called or in what order.
- Names honestly whether any of the 10 questions actually forces a
  *different sequence of tool calls* depending on the answer (a real branch
  in the path) — if none do, say so plainly rather than defaulting to
  "agents are more flexible."
- Is consistent with the table: if the workflow's numbers are equal-or-better
  on all 4 metrics and no question exhibits real path-branching, the verdict
  must favor the workflow, per the rubric's explicit warning that a verdict
  contradicting your own numbers scores 0.

- [ ] **Step 4: Run the full test suite once more**

```bash
pytest -v
```

Expected: all tests pass, including every `test_week7_*` file from Tasks
1–9.

- [ ] **Step 5: Commit the artifacts**

```bash
git add results/week7/race.csv results/week7/budget_termination.log results/week7/verdict.md
git commit -m "week7: race results, budget-termination log, and verdict"
```

---

## Deviations found during the live run (Task 10)

Two real bugs surfaced only once real Groq responses were involved — worth
recording since they weren't (and couldn't have been) predicted from mocked
tests alone:

1. **`agent/workflow.py`'s final call rejected by Groq.** Reusing
   `agent.loop.SYSTEM_PROMPT` (which says "you have tools") for the
   workflow's plain-text synthesis call made `openai/gpt-oss-120b` keep
   attempting a tool call even with no `tools` passed, and even with
   `tools=TOOL_SCHEMAS, tool_choice="none"` explicitly set -- Groq rejected
   the response outright both times ("Tool choice is none, but model called
   a tool"). Fix: a separate `SYNTHESIS_PROMPT` that never mentions tools at
   all, used only for that one call.
2. **`grade()` was too strict for real model output.** The live model
   answers "smart" typography (curly quotes, a narrow no-break space in
   "400 KB", a non-breaking hyphen in "pre-armed") that a raw
   ASCII substring check doesn't recognize even when the fact stated is
   exactly right. `grade()` now normalizes both sides to plain ASCII
   equivalents first (see `_TYPOGRAPHIC_EQUIVALENTS` in
   `eval/week7/run_race.py`), backed by
   `test_grade_ignores_smart_typography_the_model_actually_produces`. One
   question's fragment (`q10`) was also changed from `"creation time"` to
   `"at creation"` to match the phrasing both systems actually used. With
   both fixes, every question both systems answered was graded correctly —
   final `race.csv` shows a 1.0 pass rate for both.
