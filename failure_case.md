# Failure Case: Injected HTTP 500 on deprecation_worker

## Setup

- Case: `q04` -- "In GitHub API version 2025-06-01, what parameter replaces the deprecated single assignee field when creating an issue?"
- Injected failure: `deprecation_worker` raises `RuntimeError("HTTP 500: deprecation_worker service unavailable")` on every attempt (simulates the worker's service being down).
- Fact only this worker could normally supply: `assignees`

## What the orchestrator actually did

- Attempts made against `deprecation_worker`: 2
- Error recorded for this hop: `HTTP 500: deprecation_worker service unavailable`
- Resulting task state: `paused_input_required`
- Message returned to the user:

> I can't confirm this from the deprecation/version specialist right now (HTTP 500: deprecation_worker service unavailable, after 2 attempt(s)). Do you want me to answer using only the code-sample specialist's documentation search, or wait and try again later?

## Classification

- **Retried:** YES -- retried once (per handoffs.log attempts field) before giving up.
- **Task lifecycle outcome:** PAUSED: input-required -- the orchestrator stopped and asked the user how to proceed, instead of guessing or quietly degrading.
- **Hallucinated:** NO -- the pause message is a fixed template, not another LLM call, so it cannot state a fact it never confirmed.
