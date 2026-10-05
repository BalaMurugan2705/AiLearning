# error_before_after.md

Same question, same model (`openai/gpt-oss-120b` via Groq), same real `search_documentation`
tool on `docs_server.py` (your own server) — only the docstring + the tool's handling of an
unindexed API version changed. Live runs, raw transcripts in `transcript_before.json` /
`transcript_after.json` (captured with `capture_error_transcript.py`).

**Question asked both times:**
> What are the body parameters for create_issue in API version 2026-01-01, and is anything
> deprecated at that version?

(2026-01-01 is not one of the two API versions this server has indexed: 2022-11-28, 2025-06-01.)

## Before

Old docstring ("Search the indexed developer documentation... Args: query, k") and old
`search_docs()`, which always returns the nearest semantic match with no signal about which
versions are actually indexed.

1. Model calls `search_documentation(query="GitHub API 2026-01-01 create_issue body parameters")`
   → gets back prose about the doc's table of contents (2022-11-28 / 2025-06-01), not an error.
2. Model retries: `search_documentation(query="2026-01-01 create issue GitHub API")`
   → gets back a chunk about the real `assignee`→`assignees` deprecation at 2025-06-01, with no
   flag that this is the wrong version.
3. Model retries again: `search_documentation(query="2026-01-01 \"Create an issue\"")`
   → gets back the 2025-06-01 endpoint spec itself.
4. **Burns all 3 tool-call turns re-searching and never answers** (`result.answer = None`). At no
   point does the tool tell the model "2026-01-01 isn't indexed" — it can't distinguish "weak
   match" from "this version doesn't exist," so it keeps trying variations of the same query.

## After

New docstring states explicitly which versions are indexed and what an unindexed-version result
looks like; `search_docs()` now detects a version token in the query that isn't in the indexed set
and returns `{"results": [], "error": "No documentation indexed for API version(s) 2026-01-01.
Latest indexed version is 2025-06-01. Known indexed versions: 2022-11-28, 2025-06-01. ..."}`
instead of silently searching anyway.

1. Model calls `search_documentation(query="create_issue body parameters version 2026-01-01")`
   (forced on this turn so we can see the handling) → gets back the `error` field above.
2. **Model answers immediately, correctly, in one tool call:**
   > "I'm sorry—I don't have documentation for API version 2026-01-01. The indexed versions
   > available are 2022-11-28 and 2025-06-01. Could you let me know which of those versions
   > you'd like the information for?"

## Why this matters

Before: the model can't tell "no docs for this version" from "weak match," wastes its entire tool
budget re-querying, and never surfaces the real problem to the user. After: the same failure is
recoverable in a single turn — the model gets a specific, actionable reason and asks the user to
pick a version that actually exists, instead of guessing or stalling.
