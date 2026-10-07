# Week 10 Progress Log (plain English)

Running notes of what we did, step by step, updated as we go. Code is
copy-pasted and run by the user; this file just tracks what each piece is
for and what happened when it ran.

## Decisions made

- The task doc says to race against "the 10 Week-6 evaluation cases", but
  `eval/week6/` is a different domain (SDK doc RAG questions) that has
  nothing to do with the current GitHub-API tool-using agent. Decided to
  use `eval/week8/cases.json` instead — it already has exactly 10 questions
  in the right domain, with a working single-agent harness
  (`eval/week8/trajectory_eval.py`) we can reuse.

## Step 1 — Specialist workers (done)

File created: `agent/squad.py`

- `DeprecationWorker` — only has `get_openapi_spec` and `check_deprecation`
  tools. Answers exact-parameter and deprecation/version questions. This is
  the worker we'll later force to fail with a fake HTTP 500.
- `CodeSampleWorker` — only has `search_docs`. Answers prose questions and
  is told to include a short code snippet.
- Both are thin wrappers around the existing `run_agent` single-agent loop
  (same token/cost/latency tracking you already have), just with a
  narrower toolset and a role-specific system prompt.

Status: DONE. User confirmed the import works.

## Step 2 — Orchestrator (done)

Added to `agent/squad.py`: `run_squad()`, `SquadResult`, and the
`handoffs.log` writer.

- Calls the deprecation worker first (with one retry built in, ready for
  Step 5's failure test), then the code-sample worker, then makes one more
  plain LLM call ("synthesis") that re-sends both specialists' full
  answers so the model can merge them into one reply.
- Every one of those three steps ("hops") gets one line appended to
  `handoffs.log` at the repo root, recording which hop, pass/fail, and
  token count.
- Confirmed working with a real smoke-test call.

### Added afterward: routing step (Hop 0)

User asked: with no routing, every question goes to both workers every
time — is that intentional? Decided to add a routing decision instead of
always calling both.

- Added `_decide_route()`: one more small LLM call before the workers run,
  where the model is shown both workers' job descriptions and replies
  with a single word (`deprecation_worker`, `code_sample_worker`, or
  `both`) deciding who actually gets called. Logged as
  `orchestrator->routing_decision` in `handoffs.log`.
- Fail-safe: if the model's reply doesn't clearly match either worker
  name, default to calling both rather than silently calling neither.
- Skipped workers are explicit in the synthesis step, not silently empty
  (`"[skipped by router: ...]"` placeholder text).

**Found and fixed a real routing bug along the way:** the question "What
is the maximum file size limit for rendering Markdown?" was first
misrouted to `deprecation_worker`. Root cause: `render_markdown` really
is a named endpoint in this system, so the router reasonably guessed
"endpoint question → deprecation_worker" — but that worker's tools can
only return a parameter list or deprecation status, never a general fact
like a file-size limit. Naming an endpoint isn't the same as the question
being answerable by those tools. Fixed by rewriting
`ROUTING_SYSTEM_PROMPT` with few-shot examples that explicitly teach this
distinction (examples use made-up questions, not the real 10 race
questions, so the router isn't tuned to the test set). Re-tested: now
routes correctly.

This is worth remembering for `verdict.md` later — it's a real example of
multi-agent misrouting risk, found live, not hypothetical.

## Step 3 — Race harness (done)

Created `eval/week10/race.py` (plus `eval/week10/__init__.py`). Hit a real
snag along the way: a stray empty file had been created at `eval/week10`
(not a folder), and the actual code first landed in a misspelled
`eval/weeek10/` folder, which is why `python -m eval.week10.race` first
failed with `ModuleNotFoundError`. Fixed by deleting the stray file and
renaming the typo'd folder to `eval/week10`.

Ran the race for real. Results written to `race_table.md`:

| Metric | Single Agent | Squad |
| --- | --- | --- |
| Pass rate | 100% (10/10) | 90% (9/10) |
| p50 latency (s) | 16.54 | 23.43 |
| p99 latency (s) | 36.17 | 81.30 |
| Total tokens | 32,551 | 41,932 |
| Cost/question (USD) | $0.00067 | $0.00111 |

## Step 4 — Context re-send multiplier & bottleneck (done)

- **Multiplier:** 1.3x (41,932 squad tokens / 32,551 single-agent tokens)
- **Largest bottleneck hop:** `orchestrator->code_sample_worker` at 40.4%
  of all squad tokens -- makes sense, since that worker runs its own full
  search_docs tool loop rather than one plain call.
- Added `attribute_bottleneck()` to `race.py` so this is computed and
  appended to `race_table.md` automatically on every future run, instead
  of being a one-off manual calculation.

## Step 5 — Failure injection (done)

Created `eval/week10/failure_injection.py`. Ran it for real against case
q04 ("what parameter replaces the deprecated single assignee field...")
with `deprecation_worker` forced to raise a simulated HTTP 500 on every
attempt. Result written to `failure_case.md`:

- **Retried:** yes, once, before giving up (confirmed via handoffs.log's
  attempts field).
- **Degraded gracefully:** yes — final answer plainly told the user the
  deprecation/version info was unavailable, and still answered the parts
  it could (no code sample needed, so none was forced).
- **Hallucinated:** no — it did not state "assignees" despite that being
  the correct answer; it admitted the gap instead of guessing.

This is a genuinely good result for the squad's resilience, even though
the race numbers (Step 3) were bad overall.

## Step 6 — Verdict (done)

Created `verdict.md` at the repo root (Claude wrote this file directly on
request, rather than the usual copy-paste pattern). KILL decision, citing
pass rate, both latency percentiles, token multiplier, cost, and the
bottleneck hop, with the sunk-cost line explicitly called out as the
rubric requires.

**Note on re-running:** `eval/week10/race.py` got re-run at some point
after this, which produced a new `race_table.md` with slightly different
numbers (the model isn't perfectly deterministic run-to-run). Noticed
when checking the Context Re-Send Multiplier line and refreshed
`verdict.md` to match the latest race:

| Metric | Single Agent | Squad |
| --- | --- | --- |
| Pass rate | 90% (9/10) | 90% (9/10) |
| p50 latency (s) | 12.37 | 23.81 |
| p99 latency (s) | 31.46 | 72.44 |
| Total tokens | 29,751 | 40,010 |
| Cost/question (USD) | $0.00062 | $0.00101 |

Multiplier: 1.3x. Bottleneck: `orchestrator->code_sample_worker` at 50%
of squad tokens. Pass rate is now tied rather than squad-worse, but the
KILL verdict still holds -- same correctness for roughly double the
latency and 1.6x the cost.

All 4 required deliverables are now done and in sync: `race_table.md`,
`handoffs.log`, `failure_case.md`, `verdict.md`. Only the optional bonus
(AgentCard + A2A lifecycle mapping) remains.

**Reminder if racing again:** re-running `eval/week10/race.py` overwrites
`race_table.md` and `handoffs.log` with fresh (slightly different)
numbers every time -- re-check `verdict.md` still matches after any
re-run.

## Bonus — AgentCard & A2A mapping (done, then corrected)

Created `agentcard.md` at the repo root. First draft mapped the HTTP 500
case to `completed` (orchestrator silently degraded into a final answer).
User disagreed -- wanted it to genuinely map to `PAUSED: input-required`
(matching the task doc's own example), and wanted the real code changed
to match, not just the docs rewritten to claim something the code didn't
actually do.

**Real code change made** to `agent/squad.py`:
- `SquadResult` gained a `status` field (`"completed"` or
  `"paused_input_required"`).
- If the deprecation worker is needed and still fails after its retry,
  `run_squad` now stops immediately -- it never calls the code-sample
  worker or the synthesis step -- and returns a fixed pause message
  asking the user how to proceed. This message is a plain Python string,
  not another LLM call, so it cannot hallucinate the missing fact.
- Re-ran `eval/week10/failure_injection.py` for real; confirmed
  `failure_case.md` now shows `status: paused_input_required` with the
  exact pause message.

Updated `agentcard.md` Sections 2 and 3 to match this real behavior:
mapped to `input-required`/PAUSED (not completed, not failed), and
Section 3's protocol-value argument now ties directly to this concrete
pause instead of speaking generically.

Normal race runs are unaffected -- this new early-exit path only ever
triggers when `force_failure="deprecation_worker"` is explicitly passed,
which only `failure_injection.py` does.

## Status: Week 10 task complete

All required deliverables done and in sync: `race_table.md`,
`handoffs.log`, `failure_case.md`, `verdict.md`. Bonus done:
`agentcard.md` (now matching the real `paused_input_required` behavior).

Will add `run_squad()` to `agent/squad.py`: calls both workers, then one
LLM "synthesis" call to merge their answers, logging the token cost of
every hand-off (this is what `handoffs.log` needs later).

## Step 3 — Race harness (not started)

`eval/week10/race.py` → runs Single Agent vs Squad over the same 10 cases,
writes `race_table.md`.

## Step 4 — Context re-send multiplier (not started)

Computed from the Step 3 token totals + `handoffs.log`.

## Step 5 — Failure injection (not started)

`eval/week10/failure_injection.py` → forces `DeprecationWorker` to return
an HTTP 500 on one case, records what the orchestrator actually does
(retry / degrade / hallucinate) → `failure_case.md`.

## Step 6 — Verdict (not started)

`verdict.md` — KEEP or KILL, backed by real numbers from the race.

## Bonus (not started)

AgentCard + A2A lifecycle mapping for the HTTP 500 case.
