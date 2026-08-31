# Week 5 — Notes

## 0. Where the traces came from

There was no trace log before this week — `RAGPipeline.ask()` (`rag/pipeline.py`)
now builds and appends one JSON record per call to `eval/traces.jsonl` via
`rag/tracing.py`, unconditionally, matching production config (`app.py`'s
`/api/ask` uses the same `ask()` with no rerank and no `sdk_version` filter).
Each record carries: `trace_id`, `timestamp`, `question`, `strategy`, `k`,
`where`, `rerank`, `prompt_version` (a hash of the current system prompt),
`model` + `model_params`, `retrieved` (chunk_id + rank + dense/BM25/RRF/rerank
scores + source metadata per chunk), `refused`, `citations` +
`citation_check`, `sources`, `raw_output`, and `latency_ms`.

`eval/generate_traces.py` populated it by running 93 realistic questions
(`eval/trace_questions.py::RANDOM_POOL` — mostly version-unspecified natural
phrasing, plus explicit-version controls, out-of-corpus questions, migration
questions, compound questions, and a few aimed at the two contamination
sources sitting in `data/documents/` alongside the real SDK docs: an
unrelated 1963-line Omnumi iOS card-SDK doc, and a leftover
`W3-Task-Set-E.md` task file — both get chunked and indexed like any other
`.md` file) plus the 12 curated demo/DX-review questions
(`eval/trace_questions.py::DEMO`, the golden-set Q1–Q12 from Week 4), for
**105 total traces**, all real Groq calls, zero failures.

## 1. Replay evidence (requirement 1)

Seed `20260829` (today's date) → `random.Random(20260829).choice(sorted(all_trace_ids))`
→ **trace_id `b9b5b0e11147`**, question *"In v3, what does the retryable flag
mean on a RelayError?"* (`eval/replay.py --seed 20260829`).

Replay used only the trace record: the logged `question`, the logged
`retrieved` chunk_ids + scores, the logged `prompt_version` (confirmed to
still match the current `SYSTEM_PROMPT` hash), and the logged `model` +
`model_params`. Chunk **text** was re-fetched live by chunk_id from the
`docs_structural` collection, because the trace schema (deliberately) does
not store chunk text — see the gap noted below.

```
--- ORIGINAL ---
In v3 each `RelayError` includes a `retryable` flag that tells the client
whether the failure is safe to retry automatically; when `retryable` is true
you can schedule a retry, and when it is false you should treat the error as
non-retryable and handle it accordingly【v3:errors:structural:0】. This flag
replaces the need to infer retryability from error codes as was required in
v2【v3:errors:structural:3】.

--- REPLAYED ---
In v3 each `RelayError` includes a **`retryable`** Boolean that tells the
caller whether the failure is safe to retry—errors with `retryable=True` can
be retried, while those with `retryable=False` should not be retried and are
typically logged or re-raised [chunk: v3:errors:structural:0]
[chunk: v3:errors:structural:3].
```

**Not identical**, and that is itself the finding, not a bug in the replay:
the app never sets a temperature or seed on the Groq call
(`rag/generator.py::answer_question`), so nothing pins the sampling — the
same question, same retrieved chunks, same prompt can legitimately produce
different wording on every call. Both answers are factually consistent with
each other and with `v3/errors.md`. Interestingly, the **citation bracket
style itself differs between the two runs** (`【...】` in the original,
`[chunk: ...]` in the replay) — direct supporting evidence that the
bracket-style mode in the taxonomy is a per-call model choice, not a
property of this specific question.

**Fields that had to be added or noted as unreconstructable:**
- Added: the entire trace schema — nothing was logged before this week.
- Could not reconstruct: an exact sampling seed/temperature, because the app
  never sets one. A trace this schema logs is replayable in the sense of
  "same inputs to the same model call," never in the sense of "byte-identical
  output."
- Could not (in general) reconstruct: chunk **text** from the trace alone —
  only `chunk_id` + scores are logged, so replay depends on the store still
  holding that exact chunk_id. It did here (`missing_chunk_ids: []`), but a
  re-ingest that changed chunk boundaries would silently break this.
- Could not reconstruct, in principle, for an *older* trace: the exact
  `SYSTEM_PROMPT` text if it had since changed — `prompt_version` is a hash
  tag, not an archive, so it can prove the prompt is *different* from before
  but can't hand back the old wording. Not exercised by this trace_id
  specifically (the current prompt still matches), but it's a real gap in
  the design.

## 2. The seeded random sample of 20 (requirement 2)

Seed `20260829`. Eligible pool: 81 traces whose `question` is not one of the
12 curated demo questions (`eval/sample.py::split_pools`, run as
`python -m eval.sample`). `random.Random(20260829).sample(eligible_ids, 20)`:

```
fa96cb3538cc  b1417862b7ab  9c6a96669f38  1df8ef74e660  15f8e03f9de3
196c598b96ba  426e9dc310a2  132709d13774  15d42fcfa0cc  ff067b6ee1eb
44dc798bffb2  b84fe53eb006  41815ff225bf  72894e00f2ac  cefe4231be27
46f07e76cdb1  e7443d69a8a9  f808843f2491  e061afb41380  22b670d932c3
```

## 3. Open-coding — one sentence per trace (requirement 3, zero fixes applied)

1. `fa96cb3538cc` — *"What happens when a webhook delivery fails?"* — Answered
   fully from the four retrieved v3 webhook chunks, restating the exact retry
   count, schedule, and delivery-id dedup advice, with one valid
   `[chunk: ...]` citation.
2. `b1417862b7ab` — *"What v2 channel identifiers need to change for v3?"* —
   Answered from the migration-guide chunks, correctly stating the
   two-segment-to-three-segment channel change, with a valid citation.
3. `9c6a96669f38` — *"What is the per-minute rate limit on the /v3/messages
   endpoint?"* — Retrieved four chunks about streaming, migration, and client
   config, none mentioning a per-minute rate limit, and refused rather than
   guessing a number.
4. `1df8ef74e660` — *"How do I block or report a card as lost?"* — Answered
   the "report lost card" half with a code sample and two valid citations,
   then explicitly said it could not answer the "block a card" half rather
   than inventing an API for it.
5. `15f8e03f9de3` — *"What happens on close() if there are still buffered
   messages, and can I skip the wait?"* — Correctly described
   `drain_timeout_ms` and the `force=True` skip-the-wait option, but wrote
   both citations as `【chunk: v3:client:structural:6】` using full-width
   brackets, which the citation checker logged as zero citations.
6. `196c598b96ba` — *"What does the SDK support for Web3 transaction
   signing?"* — Answered correctly from four Omnumi chunks about the `sign`
   closure, but again used full-width `【】` citation brackets the checker
   did not recognize.
7. `426e9dc310a2` — *"Which countries is Relay legally available in?"* —
   Retrieved four unrelated v2/v3 chunks (client intro, auth, errors,
   webhooks) that don't discuss geography, and refused rather than
   fabricating a list of countries.
8. `132709d13774` — *"How does the SDK handle card activation errors?"* —
   Retrieved four Omnumi chunks whose chunk_ids suggest they touch activation
   and errors, but still answered with a full refusal — I don't know from the
   trace alone whether the actual answer just wasn't in those four chunks or
   whether the distance gate fired.
9. `15d42fcfa0cc` — *"What's the cursor expiry, and what error do I get if I
   use an old one?"* — Answered correctly and concisely with one valid
   citation.
10. `ff067b6ee1eb` — *"Does upgrading to v3 change how my application code
    authenticates?"* — Answered correctly that authentication is handled
    transparently by the SDK, but cited as `【v2:migrating-to-v3:structural:1】`
    — full-width brackets, no "chunk:" label at all — logged as uncited.
11. `44dc798bffb2` — *"In v2, what happens when you call close() on a client
    that never sent a message?"* — Answered the v2-specific close()-bugfix
    question correctly from the changelog chunk, with a valid citation.
12. `b84fe53eb006` — *"What's the max message size and how many retries does
    send() do by default?"* — Retrieved both a v2 and a v3 client chunk for
    this version-unspecified question, then answered using only v2's numbers
    (64 KiB max size, 3 total attempts) without mentioning the v3 chunk's
    different values (256 KiB, 4 attempts) at all.
13. `41815ff225bf` — *"Can I reuse an idempotency key across two different
    messages?"* — Answered by combining v2's changelog wording ("60
    seconds") with v3's `RELAY_409` error code into a single statement,
    without noting the two versions actually specify different dedupe
    windows.
14. `72894e00f2ac` — *"How do retries work when a send fails?"* — Explicitly
    split the answer into an "In v3" section and an "In v2" section, each
    with its own correct numbers and valid citations — the same kind of
    version-unspecified question that trace `b84fe53eb006` answered with
    only one version's numbers.
15. `cefe4231be27` — *"Is there a limit to how many concurrent streams I can
    open?"* — Retrieved streaming and pagination chunks that don't state a
    concurrent-stream limit, and refused rather than guessing one.
16. `46f07e76cdb1` — *"What does the priority parameter do on send()?"* —
    Answered correctly and concisely with one valid citation.
17. `e7443d69a8a9` — *"How do I handle errors from the SDK?"* — All four
    retrieved chunks were from the Omnumi iOS card SDK, and the answer
    described Omnumi's consent-flow and pre-approval error handling as "the
    SDK's" behavior with no mention that a second, unrelated Relay SDK is
    also indexed here.
18. `f808843f2491` — *"What's the difference between low, normal and urgent
    priority?"* — Two of the four retrieved chunks were from the leftover
    `W3-Task-Set-E.md` file and one was from the Omnumi doc, but the answer
    used only the correct `v3:client` chunk and ignored the other three.
19. `e061afb41380` — *"Do I need to change my webhook verification code after
    upgrading to v3?"* — Answered correctly that v3 requires the new
    `X-Relay-Signature-V3` verification, citing both the migration guide and
    the v3 webhooks page validly.
20. `22b670d932c3` — *"What are the two integration modes the SDK offers?"* —
    Answered correctly and specifically from the Omnumi doc, with one valid
    citation.

## 4. Modes — see `taxonomy.md` for the scored table.

## 5. Falsifiable, dated prediction (requirement 5)

Full text in `results/week5/PREDICTION.md`, committed **before** any fix, on
2026-08-29.

**Git commit hash: `918ac2a1827cce4c70d71786be899fc8340ef1d4`**

## 6. Why a public benchmark would have missed the top 3 modes (requirement 6)

A public RAG/QA benchmark scores against a citation format the benchmark
itself defines and checks with its own grader, so it would never catch a
model that sometimes cites in `【full-width】` brackets instead of this app's
`[chunk: id]` convention — that's a property of this app's exact prompt and
checker, not a fact about the model's general citing ability. It also
wouldn't reproduce this corpus's specific accident of having two unrelated
products (Relay and an Omnumi iOS card SDK) chunked into the same index, so
it could never surface an answer that silently resolves "the SDK" to the
wrong product. And a benchmark's questions are written by someone who already
knows which document holds the answer, so it structurally can't produce the
version-unspecified phrasing real users actually type, which is exactly what
triggers the mode where one SDK version's numbers get used without
mentioning the other.

## 7. Bonus — demo-set comparison (bonus challenge)

Bonus seed `20260829` (same seed, separate pool — `eval/sample.py`) → 10
trace_ids sampled from the 24 traces whose question is one of the 12 curated
demo/DX-review questions:

```
a4c1c4f24acc  7c27fa8c2926  6ff13a10d969  d227671f0f95  10a3dfcf36de
0adb71990338  a37111b86759  1ac340b23480  022abbde88aa  9d71572b5576
```

All 10 answers were factually correct. But the top mode from the random
sample — full-width `【】` citation brackets the checker never matches — showed
up in **3 of these 10 (30%)**, double the random sample's 15% (3/20):
`6ff13a10d969` (retry_backoff_ms default), `10a3dfcf36de` (webhook delivery
attempts), and `a37111b86759` (changelog version) all cite correctly-named,
correctly-retrieved chunks in a bracket style `verify_citations()` can't see.

**What the team has been telling itself:** every DX review has run these same
8–12 questions, watched the prose come back correct, and moved on — because
a human reading the answer sees a citation-shaped tag next to a true fact and
reads it as "cited." Nobody has been checking whether that tag is the *exact*
string the app's own grounding safeguard (`verify_citations`) can parse, and
it turns out the demo set — the questions everyone trusts most because
they're re-run most often — has the *worse* rate of the two, not the better
one. The 8/8-and-12/12-style hit-rate numbers from Weeks 3–4 were measuring
whether the right chunk got retrieved, never whether the citation the model
attached to it would survive being checked by machine, and those are two
different guarantees that have been quietly conflated.
