# Bonus: AgentCard & A2A Lifecycle Mapping

## 1. AgentCard

The capability manifest an A2A client would read to discover what this
orchestrator can do, how to call it, and what auth it needs.

```json
{
  "name": "github-api-migration-orchestrator",
  "description": "Routes GitHub REST API migration questions to a deprecation/version specialist and/or a code-sample specialist, then returns one synthesized answer.",
  "url": "https://internal.example/agents/github-migration-orchestrator",
  "version": "1.0.0",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "authentication": {
    "schemes": ["bearer"]
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "answer_migration_question",
      "name": "Answer GitHub API migration question",
      "description": "Accepts a natural-language question about GitHub REST API parameters, deprecations, version differences, or usage, and returns one plain-text answer combining whichever specialist(s) were relevant.",
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ]
}
```

- **Input/output:** plain text in, plain text out -- the orchestrator
  hides its internal tool calls and specialist hand-offs entirely; a
  caller never sees `handoffs.log` or which worker ran.
- **Auth:** a single bearer token at the orchestrator's boundary. The two
  specialists are internal implementation detail, not separately exposed
  over A2A, so they don't get their own AgentCards or auth in this
  design.

## 2. Mapping the HTTP 500 case onto the A2A task lifecycle

A2A tasks move through states: `submitted` -> `working` -> one of
`completed` / `failed` / `input-required` / `canceled`.

Our actual observed behavior (from `failure_case.md`, after fixing
`run_squad` to match this mapping for real): the orchestrator received
the question (`submitted` -> `working`), the deprecation worker failed
twice (one retry), and the orchestrator **stopped immediately** -- it did
not call the code-sample worker, did not run the synthesis step, and did
not guess. It returned this exact message and nothing else:

> I can't confirm this from the deprecation/version specialist right now
> (HTTP 500: deprecation_worker service unavailable, after 2 attempt(s)).
> Do you want me to answer using only the code-sample specialist's
> documentation search, or wait and try again later?

That maps to **`input-required` (PAUSED)**, matching the task doc's own
example almost exactly (ask the user how to proceed rather than guess).
It does **not** map to `completed` -- no answer was synthesized, no
specialist beyond the failed one was even consulted, so there is no
result to call complete. It is also not `failed`: the task did not abort
or error out to the caller; it is waiting on the caller's decision and
can resume once that arrives.

A deliberate implementation choice backing this: the pause message above
is a fixed Python string template, not another LLM call. It cannot invent
the missing parameter name because nothing ever asked a model to produce
it -- the only way this path can be dishonest is if the code itself lied
about the error, which is directly checkable by reading `run_squad`.

## 3. Protocol value: A2A vs. plain REST calls between workers

Without A2A, a plain REST integration has no standard way to say "I'm not
done, I need something from you" -- it either returns a success payload
or an HTTP error code, and the caller has to invent its own ad hoc
convention (a magic string, a custom JSON field) to distinguish "this
failed" from "this needs your input to continue," exactly like our own
`force_failure` plumbing had to invent `paused_input_required` as a
bespoke field. A2A's `input-required` is that convention standardized:
any caller -- a chat UI, a script, another agent -- can show the same
pause-and-ask behavior without custom per-integration error parsing, and
a published AgentCard means a new caller learns the orchestrator's
capabilities and auth by reading a manifest, not by probing it.
