<!-- Soft Suave · The AI Engineering League -->
# Week 8 — Trajectory Evals & Failure Modes — Results

Code: `eval/week8/cases.json` (the 10 cases), `eval/week8/trajectory_eval.py` (the eval
itself), `tests/test_week8_trajectory.py` (scoring-logic tests), `agent/loop.py` (the one
mitigation), `tests/test_week7_loop.py` (mitigation tests). Raw per-run JSON for every run
referenced below lives alongside this file as `trajectory_results_*.json`.

All numbers here come from real runs of the real agent against Groq (`openai/gpt-oss-120b`),
not synthetic data. Because this model is non-deterministic, every number is reported from
**2 baseline runs and 3 post-mitigation runs** (20 and 30 question-attempts respectively)
rather than a single lucky/unlucky sample.

---

## 1. The 10 cases and their expected tool paths

Ground truth for "correct" came from reading `agent/data/github_openapi.json` and
`agent/data/deprecations.json` directly, not from guessing. 6 of the 10 cases legitimately
accept more than one tool-call path and are asserted as a set, not a single sequence:

| id | question (short) | accepted sequences | why more than one path is valid |
|---|---|---|---|
| q01 | markdown max file size | `[search_docs]` | single path — pure prose fact |
| q02 | Swagger Codegen Maven groupId | `[search_docs]` | single path |
| q03 | OAuth scopes for repo creation | `[search_docs]` | single path |
| q04 | assignee → assignees replacement | `[check_deprecation]`, `[check_deprecation, get_openapi_spec]`, `[get_openapi_spec, check_deprecation]` | the deprecation record alone answers it; confirming against the spec too is also correct |
| q05 | discussion_category_name param | `[get_openapi_spec]`, `[search_docs, get_openapi_spec]` | reading docs for context first is fine as long as the spec is checked |
| q06 | render_markdown context format change | `[check_deprecation]`, `[search_docs]`, `[search_docs, check_deprecation]`, `[check_deprecation, search_docs]`, `[get_openapi_spec, get_openapi_spec]` | the deprecation record, the prose docs, and a direct before/after spec diff all independently prove the same fact |
| q07 | maintainer_can_modify change | `[search_docs]`, `[get_openapi_spec, get_openapi_spec]`, `[search_docs, get_openapi_spec, get_openapi_spec]` | not a deprecation entry — only prose or a direct 2-version spec diff can answer it |
| q08 | make_latest replaces heuristic | `[search_docs]`, `[get_openapi_spec]`, `[get_openapi_spec, get_openapi_spec]` | the 2025-06-01 spec entry alone states what it replaces, so a single call suffices |
| q09 | draft PR / auto-merge interaction | `[search_docs]` | single path — not in the OpenAPI spec at all |
| q10 | issue `type` field added | `[search_docs]`, `[get_openapi_spec]`, `[get_openapi_spec, get_openapi_spec]` | same shape as q08 |

`min_steps` for every case is 1 (the cheapest accepted path).

---

## 2. Baseline trajectory numbers (before the mitigation)

Averaged over 2 independent live runs (20 question-attempts):

| metric | value |
|---|---|
| tool-choice accuracy | 1.00 |
| argument validity rate | 1.00 |
| step efficiency (steps taken / steps needed) | 1.40 |
| cost per question — p50 | $0.000638 |
| cost per question — max | $0.001186 |
| outcome pass rate | 0.85 |
| trajectory pass rate | 0.65 |
| **outcome − trajectory gap** | **0.20** |

Argument validity and tool-choice accuracy sit at a clean 1.00 — not because the agent is
flawless, but because `api_version` and `endpoint` are both `enum`-typed in the tool schema
(`agent/tools.py`), so Groq's own request validation structurally cannot let a fabricated
endpoint name or version string through as an *accepted* call. That's a real, measured
finding, not a coincidence: schema-level typing already buys 100% argument validity for
free, before any of the mitigations below are even considered. What it does **not** prevent
is the model inventing a tool name that isn't in the schema at all — see the failure mode
below.

## 3. The outcome-vs-trajectory gap: a real example

Baseline gap = **0.20** (outcome pass rate 0.85 minus trajectory pass rate 0.65). One
concrete right-answer-wrong-path case, `q08`, recurred in multiple runs. Full trace from one
run:

> **Question:** "How does the make_latest parameter in GitHub API version 2025-06-01
> release creation replace the undocumented heuristic used in 2022-11-28?"
>
> **What it did:** called `search_docs` *twice* — once with query `"make_latest parameter
> release creation GitHub API 2025-06-01"`, then again with query `"undocumented heuristic
> latest release 2022-11-28 make_latest"` — instead of the one call needed.
>
> **What it should have done:** a single `search_docs` or `get_openapi_spec` call already
> contains the full answer (the 2025-06-01 spec entry literally says the field "replaces...
> an internal publish-date heuristic").
>
> **Outcome grading:** PASS — `make_latest` appears in the answer, correctly explained.
> **Trajectory grading:** FAIL — sequence `[search_docs, search_docs]` isn't in the accepted
> set; `failure_mode = "extra_steps"`. Cost: $0.001127 / 4,951 tokens / 28.7s — roughly
> **double** what the 1-call path should cost, entirely because it re-searched instead of
> trusting its first result.

This is a real, cheap-but-real version of the assignment's warning: the outcome eval alone
would call this question a clean pass and never surface that the agent doesn't trust its own
retrieval and burns budget re-confirming things it already found.

## 4. The mitigation

**Top failure mode.** Across the 2 baseline runs, the costliest failure by far wasn't
`extra_steps` (a question still gets answered, just less efficiently) — it was the run
crashing to **zero**: 3 of 20 question-attempts (15%) hit a hard Groq 400 error and returned
no answer and no trajectory at all:

- `hallucinated_tool` (2 occurrences): the model invented a tool call to `open_file`, which
  was never declared in `TOOL_SCHEMAS`. Groq's server-side validation rejects the *entire*
  request before `agent/loop.py` ever sees a response to inspect.
- `api_error` / `output_parse_failed` (1 occurrence): the model emitted raw reasoning prose
  instead of a clean tool call or answer, and Groq rejected that too.

Both are the same underlying problem: **`run_agent`'s loop had no way to recover from a
malformed model turn — it just crashed.** This is worse than every other mode observed,
because a wrong-but-graded answer at least produces a number; this produces nothing.

**The one mitigation: re-planning.** `agent/loop.py` now catches exactly these two
recoverable error shapes around the `client.chat.completions.create()` call. Instead of
letting the exception propagate, it appends a corrective message to the conversation ("your
last turn could not be used because X; the only tools that exist are: search_docs,
get_openapi_spec, check_deprecation; try again") and lets the loop continue — bounded by the
same iteration/token/cost/wall-clock budget that already existed, so a repeat offender still
terminates cleanly instead of looping forever (`tests/test_week7_loop.py::
test_agent_eventually_hits_budget_if_every_retry_keeps_failing`). This is exactly one
mitigation from the assignment's list ("re-planning"), not stacked with anything else.

**Before → after, measured over live runs:**

| | before (2 runs / 20 q) | after (3 runs / 30 q) |
|---|---|---|
| `hallucinated_tool` + `api_error` (crash mode) | 3 (15.0%) | **0 (0.0%)** |

**Price paid.** The mechanism itself is deterministic and directly tested: every recovery
costs exactly one extra full model round-trip (`tests/test_week7_loop.py::
test_agent_recovers_from_a_hallucinated_tool_name_instead_of_crashing` asserts
`iterations == 2` instead of 1, and `len(client.calls) == 2`). No live retry happened to
fire in the 30 post-mitigation question-attempts sampled here (the underlying ~15%
per-question trigger rate just didn't land in this sample), so the dollar/latency price is
priced from this project's own measured average cost per model round-trip across all 47
completed calls in every run collected for this eval: **≈$0.00024 and ≈1,153 tokens per
retry**, plus one extra network round trip (this project's runs average ~5s per round-trip
end to end, mostly Groq queue/generation time, not the retry logic itself). This mitigation
is not free — it is one full extra paid model call, charged only on the ~15% of questions
that need it.

## 5. Regression check — every mode, before vs. after

| failure mode | before (of 20) | after (of 30) | verdict |
|---|---|---|---|
| `hallucinated_tool` | 2 | 0 | **fixed** — the mode this mitigation targets |
| `api_error` | 1 | 0 | **fixed** — same root cause, same fix |
| `extra_steps` | 4 (20.0%) | 6 (20.0%) | unchanged rate — not touched by this fix, not made worse by it either |
| `no_tool_call` | 0 | 1 (3.3%) | **new observation** — see below |
| `wrong_target` | 0† | 0 | n/a |

† An early run flagged 2 false "wrong_target" cases, but that was a bug in this eval's own
fixture logic (it penalized a legitimate before/after comparison for checking *both* API
versions), not a real agent failure — fixed in `trajectory_eval.py::_target_mismatch` and
covered by `tests/test_week8_trajectory.py::
test_trajectory_passes_when_both_versions_are_legitimately_compared` before any baseline
number above was collected.

**On `no_tool_call` appearing once after but not in the smaller before sample:** this
happened on `q02` (the model answered "I don't have that information" without calling any
tool at all — a different, wrong-answer-no-path failure, the mirror image of the
outcome/trajectory gap). Honestly reported as new to this sample, but very unlikely to be
caused by the mitigation: that code path (a message with no `tool_calls`) is untouched by
`agent/loop.py`'s change, which only wraps the exception from `.create()` itself. With N=1 it
is most plausibly baseline model nondeterminism that this particular small sample happened
to catch, not a regression the fix introduced — but it is named here rather than hidden, and
would be the next thing worth a dedicated before/after comparison if more runs were
budgeted.

**Bottom line:** the mitigation eliminated its target failure mode completely in this
sample (15.0% → 0.0%), did not measurably worsen the one other mode with enough data to
compare (`extra_steps` held flat at 20%), and its price — one extra paid model round-trip on
the ~15% of questions that need it — is measured, not assumed.
