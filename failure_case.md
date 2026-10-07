# Failure Case: Injected HTTP 500 on deprecation_worker

## Setup

- Case: `q04` -- "In GitHub API version 2025-06-01, what parameter replaces the deprecated single assignee field when creating an issue?"
- Injected failure: `deprecation_worker` raises `RuntimeError("HTTP 500: deprecation_worker service unavailable")` on every attempt (simulates the worker's service being down).
- Fact only this worker could normally supply: `assignees`

## What the orchestrator actually did

- Attempts made against `deprecation_worker`: 2
- Error recorded for this hop: `HTTP 500: deprecation_worker service unavailable`
- Final synthesized answer:

> The information you’re looking for isn’t currently available—the deprecation/version specialist was unable to retrieve details about the replacement for the deprecated **single‑assignee** field in the **2025‑06‑01** GitHub API version.  

Because the question didn’t require a code example, no sample is provided. If you have any other details or a different question, feel free to let us know!

## Classification

- **Retried:** YES -- retried once (per handoffs.log attempts field) before giving up.
- **Degraded gracefully** (admitted the information was unavailable): YES
- **Hallucinated** (stated the expected fact `assignees` anyway, with its only real source broken): NO
