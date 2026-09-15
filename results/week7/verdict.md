# Verdict

## Assignment verdict (the required 10-question race)

Over the same 10 questions, agent and workflow both scored a 1.0 pass rate
— every first-pass "failure" was a substring-grading bug (smart typography,
one overly narrow fragment), not a content error. With grading fixed, the
workflow matched the agent's correctness at roughly half the tokens
(14,393 vs 29,947) and half the cost ($0.00034 vs $0.00062/question). The
agent was faster this run (p50 6.5s vs 10.6s), but pass rate swung a full
question on a repeat run from pure model nondeterminism, so that latency
edge isn't trustworthy either.

Decision rule: does the correct tool-call *sequence* vary by input? No. All
10 questions, including the 5 needing a before/after version comparison,
resolved from the same fixed search→spec→deprecation→answer path;
`search_docs` already surfaces both versions' prose in one call. Nothing
here forces a real branch, so on this table the workflow wins.

## Extended findings (30 more questions, pulled from the existing golden sets)

Beyond the assignment's required 10, agent and workflow were also raced over
`gs_easy.json` and `gs_medium.json` (15 questions each, unmodified from the
project's existing golden sets — including their "not in the docs, refuse"
negative cases and pure Swagger-Codegen-CLI questions the tools don't cover
at all). `gs_hard.json` was intentionally not run. Full numbers:
`results/week7/race_easy.csv`, `race_medium.csv`, and the per-question
`race_details_*.json` files.

| set | system | pass rate | p50 latency | total tokens | cost/question |
|---|---|---|---|---|---|
| easy (15) | agent | 11/15 (0.73) | 12.1s | 54,086 | $0.00066 |
| easy (15) | workflow | 13/15 (0.87) | 10.1s | 20,778 | $0.00028 |
| medium (15) | agent | 10/15 (0.67) | 14.0s | 69,408 | $0.00083 |
| medium (15) | workflow | 10/15 (0.67) | 11.0s | 22,020 | $0.00032 |

On this harder, broader, mixed-topic question set the workflow ties or
**beats** the agent on correctness while still using roughly a third of
the tokens and cost — the opposite of what "the agent is more capable but
more expensive" would predict. Digging into the failures explains why, and
none of it is the grading bug that inflated the first-pass numbers on the
required 10 (that bug is fixed here too — see `run_race.py`'s
`_TYPOGRAPHIC_EQUIVALENTS` and `REFUSAL_KEYWORDS`):

- **The agent burned its entire wall-clock budget with no answer at all**
  on 5 of 30 questions (2 "not in the docs" easy questions, 3 medium
  Swagger-CLI questions) — it kept searching/reasoning past 60s before
  being cut off. The workflow, having no loop, never has this failure mode.
- **A "fabricated endpoint" trap question broke the agent outright.** One
  medium question deliberately asks about a GitHub endpoint that doesn't
  exist. The agent tried to call `get_openapi_spec` with a made-up
  endpoint name; Groq's own enum validation rejected the entire API call
  (400 error) before our code's graceful "no such endpoint" handling ever
  ran. The required enum constraint did its job (no fabricated argument
  reached our tool), but the failure surfaced as a hard crash instead of a
  clean answer — caught now by a per-question try/except in `run_system()`
  so one bad question no longer takes down the whole batch.
- **The agent's system prompt is scoped too narrowly.** It's framed as a
  "GitHub API migration" helper, so on a legitimate, in-corpus Swagger
  Codegen question it flatly refused: *"I can only help with questions
  about migrating code between GitHub API versions."* The workflow's
  separate, topic-agnostic synthesis prompt had no such blind spot and
  answered the same question correctly.
- **Both systems share one real weakness**: `search_docs` itself fails to
  surface a handful of specific Swagger Codegen config-default facts
  (e.g. a `packageVersion` default, `allowUnicodeIdentifiers`'s default),
  missed by both agent and workflow alike — a retrieval gap, not an
  architecture difference.

None of this changes the core verdict — it reinforces it. Even across 40
questions spanning two unrelated document topics, not one required a
genuinely different *sequence* of tool calls; the workflow's fixed
search→spec→deprecation→answer order, with irrelevant spec/deprecation
context simply ignored on off-topic questions, was sufficient every time.
The agent's freedom to loop, rephrase, and reason longer bought it nothing
in accuracy here, and directly caused three of its own failure modes
(budget exhaustion, a fabricated-argument crash, and prompt-scoping
over-refusal) that the workflow structurally cannot have.
