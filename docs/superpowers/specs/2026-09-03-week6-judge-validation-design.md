# Week 6 — Validating the docs-answer judge before trusting its number

**Date:** 2026-09-03
**Task:** `task/W6-Task-Set-E.md` — Week 6 Practical, Task Set E (100 marks)
**Builds on:** Week 5 taxonomy (`results/week5/taxonomy.md`), Week 5 prediction
(`results/week5/PREDICTION.md`), the existing `eval/` harness.

---

## 1. Problem and scope

The task assumes an LLM judge already prints a helpfulness score that nobody has
checked against a human. This repo has no judge at all. So Week 6 must both
author the judge and validate it — and the validation is only meaningful if the
first judge is written as an honest first draft rather than pre-tuned to agree
with the labels it will be measured against.

The deliverable is five things that have to happen in a provable order:

1. An eval set of 25+ cases, each tagged with exactly one Week-5 taxonomy mode,
   including regression cases replayed verbatim from real failed traces, runnable
   by one command that prints pass rate **by mode**.
2. At least 2 criteria moved out of the judge into deterministic assertions and
   deleted from the judge prompt, with the assertion/judged-criteria counts
   reported.
3. 25 hand labels on the judge's single binary criterion, committed **before**
   the judge is ever run, with commit-order evidence.
4. Judge agreement measured, then the judge prompt iterated using two of its own
   disagreements as few-shot examples, and agreement re-measured — reported as
   two numbers.
5. A one-sentence written prediction filed before iterating, then scored
   honestly against what actually happened.

## 2. Non-goals

- **No RAGAS.** The bonus (faithfulness + context precision) is deferred until
  the graded requirements are landed and verified. It pulls in a heavy
  dependency tree and its own LLM calls.
- **No Week-5 citation-regex fix.** `rag/generator.py:38` `_CITATION_RE` is still
  ASCII-only, so the Week-5 predicted fix has not landed. It stays unlanded here
  deliberately: the frozen answer snapshot should reflect the system as it was
  measured in Week 5, and landing a generation-path change mid-week would mean
  the 25 labels describe a system that no longer exists. Tracked as a Week-5
  loose end in §16, not as Week-6 scope.
- **No app/UI work.** The rubric awards zero for polish.

## 3. Judge lineage: v0 → v1 → v2

Three prompts, not two. `judge_v0` exists so that requirement 2's "delete those
criteria from the judge prompt" is a real diff against a real prior state rather
than a claim about a judge that never existed.

### judge_v0.txt — the naive multi-criteria judge

Six criteria, bundled, scored together. This is the stand-in for "the number
nobody checked":

| # | v0 criterion | Fate |
|---|---|---|
| 1 | The answer states which SDK version it applies to | → assertion A4 |
| 2 | Any code sample is syntactically valid Python | → assertion A1 |
| 3 | Every SDK symbol named in the answer exists | → assertion A2 |
| 4 | Every HTTP endpoint path named exists in the API spec | → assertion A3 |
| 5 | Deprecated v2 features are not recommended without a migration note | → assertion A5 |
| 6 | A developer on the version asked about gets correct, actionable guidance | **stays** |

### judge_v1.txt — the post-split single-criterion judge

v0 with criteria 1–5 physically deleted, leaving criterion 6 as one binary
verdict. This is what gets hand-labelled against and what produces
`agreement_before`.

The single criterion:

> Would a developer working in the SDK version this question is about be able to
> act on this answer and get correct behaviour?

The prompt explicitly instructs the judge **not** to consider code syntax,
symbol spelling, endpoint existence, version-label presence, or citation
formatting, because those are checked deterministically elsewhere. Without that
instruction the judge silently re-litigates the assertions and the split is
cosmetic.

Output contract, parsed strictly:

```
VERDICT: PASS
REASON: <one line>
```

A response that does not match is recorded as a parse failure, not coerced into
a verdict.

### judge_v2.txt — v1 plus two of its own disagreements

Requirement 4. The two few-shot examples must come from `judge_v1`'s own
disagreements with the human labels — never from cases chosen for being
illustrative.

### Judge model

The judge runs on a **different model than the answerer**: answers come from
`openai/gpt-oss-120b` (the `GROQ_MODEL` default, matching the logged traces), the
judge on `llama-3.3-70b-versatile` via a new `JUDGE_MODEL` env var. Same-model
judging invites self-preference bias, which would make agreement measure family
resemblance rather than correctness. Temperature 0.

## 4. The eval set

`eval/week6/cases.jsonl`, 25 cases, five per Week-5 mode. Mode names are the
Week-5 taxonomy names verbatim so the two write-ups line up.

| Mode tag | n | Regression replay included |
|---|---|---|
| `citation-format` | 5 | `15f8e03f9de3` |
| `version-ambiguity` | 5 | `b84fe53eb006` |
| `cross-product-bleed` | 5 | `e7443d69a8a9` |
| `unexplained-refusal` | 5 | `132709d13774` |
| `clean` | 5 | — (authored from `eval/golden_set.jsonl`) |

Four regression cases against a required minimum of two. "Replayed verbatim"
means the question **and** every execution parameter (`k`, `where`, `strategy`,
`rerank`, `model`, `model_params`) are copied out of the trace record by
`build_cases.py --from-trace <trace_id>`, never retyped by hand. The Week-5
trace schema already logs all of them.

Case schema:

```json
{
  "case_id": "W6-07",
  "question": "What's the default retry backoff for Client.send()?",
  "mode": "version-ambiguity",
  "origin": {"kind": "replay", "trace_id": "b84fe53eb006"},
  "version_sensitive": true,
  "sdk_version_intent": "unspecified",
  "retrieval":  {"k": 4, "where": null, "strategy": "structural", "rerank": false},
  "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}},
  "notes": "Week-5 example trace for the one-version-only mode."
}
```

`origin.kind` is `replay` or `authored`; authored cases carry
`{"kind": "authored", "basis": "golden_set:Q3"}` so every case's provenance is
machine-readable.

The two version fields do different jobs and are not redundant.
`version_sensitive` is a boolean gate that decides whether **A4 applies** to the
case. `sdk_version_intent` records what the question is *about* (`v2`, `v3`, or
`unspecified`) and feeds the disagreement analysis, not any assertion.

Note that `sdk_version_intent: "unspecified"` does **not** imply
`version_sensitive: false` — it is the opposite. The Week-5
`version-ambiguity` mode is precisely "answers a version-unspecified question
with only one version's numbers", so those cases are the ones where the answer
most needs to state which version it is describing. Every case in that bucket
carries `version_sensitive: true`.

## 5. Frozen answer snapshot

`eval/week6/snapshot.py` generates the 25 answers **once**, deliberately, and
writes `eval/raw/answers_25.json`. The one-command eval re-scores that file; it
does not regenerate answers.

This is the load-bearing decision of the whole design. If answers regenerated
per run, the 25 hand labels would silently decay and the
`agreement_before → agreement_after` delta would mix judge changes with answer
drift — the number would stop meaning anything. Frozen answers make the delta
attributable to the judge prompt alone, which is the entire point of the
exercise.

```json
{
  "answers_sha256": "<sha256 of the canonicalised answers array>",
  "generated_at": "2026-09-03T…",
  "pipeline": {"strategy": "structural", "collection": "docs_structural", "prompt_version": "sysprompt-…"},
  "answers": [
    {"case_id": "W6-07", "question": "…", "mode": "version-ambiguity",
     "retrieved": [{"chunk_id": "…", "rank": 0, "dense_distance": 0.27, "bm25_score": 19.0, "source_file": "v2/client.md"}],
     "raw_output": "…", "refused": false, "citations": [], "citation_check": {…},
     "prompt_version": "sysprompt-…", "model": "openai/gpt-oss-120b",
     "model_params": {"max_tokens": 2048}, "latency_ms": 1377.3,
     "answer_sha256": "…"}
  ]
}
```

`answers_sha256` is the anchor: it is copied into the labels file and into every
judge run, so any artifact can be checked against the exact answer text it was
produced from.

## 6. The five deterministic assertions

`eval/week6/assertions.py`. No LLM calls, no network.

**A1 `code_parses`** — extract every ` ```python ` fence from the answer and run
`ast.parse` on each. A `SyntaxError` fails the assertion, naming the fence index
and the error. Applicable only when the answer contains ≥1 python fence.

**A2 `symbols_exist`** — pattern-scoped, not vocabulary-scoped. The corpus
backticks `str`, `int`, `None`, `id`, `message`; checking every backticked token
against an allowlist would fail constantly on ordinary prose. So A2 inspects only
tokens matching SDK-symbol families:

- error codes — `RELAY_\d{3}`, `AUTH_[A-Z_]{3,}`
- exception/class names — `Relay[A-Z]\w*`, `Signature[A-Z]\w*`, `Stream[A-Z]\w*`, `\w*Cache`
- qualified methods — `Client\.\w+\(\)`
- parameter names — snake_case identifiers carrying **at least one underscore**:
  `[a-z][a-z0-9]*(_[a-z0-9]+)+`

The membership test and the shape test are deliberately separate. A token is
**selected for checking** by its *shape* (the patterns above) and then **passes or
fails** on its presence in `symbols.json`. Selecting tokens by presence in the
symbol table instead would be circular — nothing could ever fail.

Two exclusions follow from the shape rules and are worth stating because they are
what keeps the false-positive rate at zero on ordinary prose:

- Bare unqualified calls (`close()`, `print()`, `verify()`) are **not** checked.
  Method names are checked only in `Client.x()` form. An unqualified-call rule
  would fail on stdlib calls that legitimately appear in code samples, and the
  distinctive fabrications A2 exists to catch are qualified or code-shaped anyway.
- The required underscore excludes single-word tokens — `str`, `int`, `None`,
  `True`, `False`, `id`, `code`, `message`, `channel` — all of which the corpus
  backticks in ordinary prose.

So a fabricated `RELAY_777`, `Client.sendBatch()`, or `retry_delay_ms` fails,
while `str` and `message` are never examined. Authority is
`eval/spec/symbols.json`.

**A3 `endpoints_exist`** — every `/vN/...` path or `METHOD /path` mentioned in the
answer must appear in `eval/spec/relay_openapi.json`. The entire corpus contains
exactly one endpoint path (`POST /v3/auth/token`, `data/documents/v3/auth.md:15`),
so this assertion will apply to only a handful of the 25 cases. It is kept
because "how do I authenticate in v3?" is precisely where a model invents
`/v3/tokens/refresh`. It reports its own applicable count so the small N is
visible in the write-up rather than hidden.

**A4 `version_stated`** — for cases with `version_sensitive: true`, the answer must
explicitly name `v2` or `v3`. This checks **stated-ness only, never
correctness**: whether a version is named is deterministic, whether it is the
*right* version is judgement and stays with the judge. That is the seam between
the two halves of the split.

**A5 `deprecation_has_migration_note`** — for each entry in
`eval/spec/deprecations.json` whose match pattern hits the answer, require that
the entry's replacement symbol or a migration-note phrase appears within the
same paragraph. A deprecated thing recommended with no migration signal fails.

"Same paragraph" means the blank-line-delimited block containing the match; when
the answer contains no blank lines, a ±300-character window around the match is
used instead. The window is defined in the spec rather than left to the
implementation because it is the difference between a strict and a lenient
assertion, and that should not be an accident of code.

### Skipped ≠ passed

An assertion that does not apply to a case records `skipped`, never `pass`.
Counting N/A as a pass would let A3 alone donate ~20 free passes to the table and
manufacture a pass rate out of nothing.

### The reported counts

**5 deterministic assertions vs 1 judged criterion**, down from 6 judged
criteria in `judge_v0`.

## 7. Spec artifacts

`eval/spec/`, all three regenerable or traceable to a source line:

- **`symbols.json`** — generated by `eval/spec/build_symbols.py` from
  `data/documents/v2` and `v3`. Records, per symbol, the versions it appears in
  and the source files. Script-generated so it cannot drift from the docs; A5
  reuses the per-version field.
- **`relay_openapi.json`** — a minimal OpenAPI document containing the one real
  path, derived from `v3/auth.md:15`. Deliberately not padded with invented
  paths: an assertion whose authority was fabricated is worse than no assertion.
- **`deprecations.json`** — **hand-curated**, because it cannot be script-derived.
  The v2-vs-v3 backticked-symbol diff yields exactly one v2-only symbol
  (`RELAY_401`); everything else that was removed exists only as prose in
  `data/documents/v2/migrating-to-v3.md`. Each entry cites its source file and
  line:

  | deprecated | kind | replacement | source |
  |---|---|---|---|
  | `RELAY_401` | error code | `AUTH_TOKEN_EXPIRED` / `AUTH_SCOPE_DENIED` | v2/errors.md → v3/errors.md |
  | offset pagination (`offset`, `page_offset`, "page offset") | pagination | `next_cursor` / `from_cursor` | migrating-to-v3.md |
  | two-segment channel `org/topic` | identifier format | `org/team/topic` | migrating-to-v3.md |
  | long-lived key on every request | auth pattern | bearer token via `POST /v3/auth/token` | migrating-to-v3.md, v2/auth.md |
  | v2 fixed-delay retry (500 ms, 3 attempts) | defaults | `retry_backoff_ms=2000`, `retry_backoff_factor`, 4 attempts | migrating-to-v3.md, v2/CHANGELOG.md |
  | v2 webhook signatures | signing scheme | v3 re-registration + `verify()` | migrating-to-v3.md |

## 8. Blind labeling protocol

`eval/week6/label.py`. Shows one case at a time — `case_id`, question, retrieved
chunk previews, the answer text — and prompts `y` / `n` / `?` (re-display) /
`q` (save partial and quit). It writes `eval/week6/labels_25.json`.

Two properties make it blind rather than nominally blind:

1. `label.py` **imports nothing from `judge.py`** and never reads a judge run
   file. There is no code path by which a verdict could be displayed.
2. It **aborts** if `eval/raw/judge_v1_run.json` already exists, unless run with
   `--force-relabel`, which stamps `"blind": false` into the output file and is
   therefore self-incriminating rather than silently permissive.

The criterion text shown to the labeler is **read out of `judge_v1.txt`** rather
than duplicated, so the human and the judge cannot drift onto different
questions. Its sha256 is recorded.

```json
{
  "labeler": "ajithkumar.palani@softsuave.com",
  "criterion_text": "Would a developer working in the SDK version this question is about …",
  "criterion_sha256": "…",
  "answers_sha256": "…",
  "blind": true,
  "started_at": "…", "completed_at": "…",
  "labels": [{"case_id": "W6-07", "label": false, "seconds": 41, "note": "gives the v2 number for a version-unspecified question"}]
}
```

Seeing `judge_v1.txt`'s criterion before labeling is correct and required —
agreement is only defined if both parties answered the same question. Blindness
concerns the judge's **verdicts**, not its criterion.

## 9. Judge runner and the ordering guard

`eval/week6/judge.py` takes a prompt file, scores all 25 snapshot answers at
temperature 0, and writes `eval/raw/judge_v1_run.json` / `judge_v2_run.json`.

Before its first model call it enforces:

```
git log -1 --format=%H -- eval/week6/labels_25.json   # must be non-empty
git diff --quiet HEAD -- eval/week6/labels_25.json    # must be clean
```

Uncommitted or dirty labels abort the run with an explanatory message. The run
file then records the proof:

```json
{
  "judge_prompt": "results/week6/judge_v1.txt",
  "judge_prompt_sha256": "…",
  "judge_model": "llama-3.3-70b-versatile",
  "temperature": 0,
  "answers_sha256": "…",
  "labels_commit": "<git hash of commit C2>",
  "labels_sha256": "…",
  "run_at": "…",
  "verdicts": [{"case_id": "W6-07", "verdict": "FAIL", "reason": "…", "raw": "…"}]
}
```

This inverts the weakest-evidence requirement into the strongest one. The judge
run physically contains a commit hash that could only exist if the labels were
committed first — not a timestamp a skeptical grader can wave away.

## 10. Agreement math

`eval/week6/agreement.py` reports, for each judge version:

- **raw agreement** — matches / 25, as a percentage. These are the two required
  numbers.
- **confusion matrix** — TP / FP / FN / TN, human label as reference.
- **Cohen's κ**, and the human label base rate.
- **disagreements broken out per mode.**

κ is not decoration. If the labels come out 22 PASS / 3 FAIL, a judge that
answers PASS unconditionally scores 88% raw agreement while being worthless.
That is the task's own "reporting one overall pass rate" mistake one level up,
and raw agreement alone cannot see it. Where κ is low and agreement high, the
write-up says so explicitly.

## 11. Iteration and the prediction

Order, enforced by commit sequence:

1. `judge_v1` runs → `agreement_before`.
2. Its disagreements are read by hand and written up in
   `results/week6/disagreements.md`: case_id, question, answer excerpt, human
   label, judge verdict and reason, **an explicit verdict on who was right**, and
   what it implies about the prompt. At least 2, per the rubric.
3. `results/week6/prediction.txt` — one sentence on what the iteration will fix,
   committed **alone**, before `judge_v2.txt` exists.
4. Two of the disagreements become few-shot examples in `judge_v2.txt`.
5. `judge_v2` runs → `agreement_after`.
6. The prediction is scored honestly, **including where it was wrong**, in the
   generated results.

Two anti-gaming measures, both mechanical:

- `labels_25.json` is never edited after commit C2. A test asserts its sha256
  still equals the value recorded in `judge_v1_run.json`, so relabelling to
  inflate agreement becomes a test failure rather than a matter of conscience.
  This is the task's "you moved the ruler, not the thing being measured" mistake.
- The two few-shot cases stay **inside** the `agreement_after` denominator —
  excluding them would be self-scoring. Because those two are now nearly
  guaranteed to agree, the results also report agreement over the 23
  non-few-shot cases as a secondary number, so the reader can see how much of
  the delta is genuine generalisation.

## 12. The one command

```
python -m eval.week6.run
```

Scores the frozen snapshot with the assertions, runs whichever judge prompts
exist, and prints:

```
=== Pass rate by mode (n=25) ===
mode                   n   assert   judge   overall
citation-format        5    5/5      4/5      4/5    80%
version-ambiguity      5    2/5      1/5      1/5    20%
cross-product-bleed    5    4/5      2/5      2/5    40%
unexplained-refusal    5    5/5      3/5      3/5    60%
clean                  5    5/5      5/5      5/5   100%
----------------------------------------------------------
TOTAL                 25   21/25    15/25    15/25   60%

=== Assertions vs judged criteria ===
deterministic assertions: 5    judged criteria: 1    (judge_v0 had 6)

=== Judge agreement with 25 human labels ===
agreement_before (judge_v1): __%   kappa __    [labels commit <hash>]
agreement_after  (judge_v2): __%   kappa __
```

(Layout illustrative; every number comes from the raw JSON.)

A case passes overall only if **every applicable assertion passes and the judge
returns PASS**. Pass rate is reported per mode and never pooled into a single
headline — Week 5's lesson, and the task's last listed Common Mistake.

Writes `eval/raw/week6.json` and renders `results/week6-results.md` through
`eval/week6/report.py`, following the existing repo convention that results
markdown is generated and never hand-edited.

Flags: `--regenerate-answers` (deliberate re-snapshot, refuses if labels exist
unless `--i-know-this-invalidates-labels`), `--judge v1|v2|both`,
`--no-judge` (assertions only; needs no API key).

## 13. File layout

```
eval/week6/
  __init__.py
  cases.jsonl        25 mode-tagged cases with machine-readable provenance
  build_cases.py     --from-trace lifts replay params out of traces.jsonl
  snapshot.py        generates the frozen answer set
  assertions.py      A1–A5, no LLM calls
  judge.py           prompt-file runner + ordering guard
  agreement.py       raw agreement, confusion matrix, Cohen's kappa
  label.py           blind labeling CLI + blindness guard
  report.py          renders results/week6-results.md
  run.py             the one command
  labels_25.json     committed alone, in its own commit
eval/spec/
  build_symbols.py   corpus -> symbols.json
  symbols.json       generated
  relay_openapi.json derived, one real path
  deprecations.json  hand-curated, each entry citing its source
eval/raw/
  answers_25.json  judge_v1_run.json  judge_v2_run.json  week6.json
results/week6/
  judge_v0.txt judge_v1.txt judge_v2.txt
  prediction.txt disagreements.md
results/week6-results.md   generated
tests/
  test_week6_assertions.py test_week6_agreement.py test_week6_ordering.py
```

## 14. Commit choreography

The order is graded, so it is designed rather than incidental:

| # | Commit | Contents |
|---|---|---|
| C1 | `week6: cases, spec artifacts, assertions, judge v0->v1 split, blind labeling CLI` | everything except labels, prediction, judge_v2, and any judge run output. Includes `judge_v1.txt` (its criterion is needed to label against) but no run. |
| C2 | `week6: 25 blind labels (pre-judge)` | **`labels_25.json` alone.** Nothing else in this commit. |
| C3 | `week6: judge_v1 run + agreement_before` | `judge_v1_run.json` (embedding C2's hash), disagreements.md |
| C4 | `week6: prediction before judge iteration` | **`prediction.txt` alone.** |
| C5 | `week6: judge_v2 + agreement_after + results` | `judge_v2.txt`, `judge_v2_run.json`, `week6.json`, `results/week6-results.md` |

Grader verification, two commands:

```
git log --oneline --reverse -- eval/week6/labels_25.json eval/raw/judge_v1_run.json
jq -r .labels_commit eval/raw/judge_v1_run.json
```

The first shows the labels commit strictly precedes the judge run; the second
returns a hash that matches it.

## 15. Testing

TDD, following the existing `tests/` layout and `pytest` setup.

- `test_week6_assertions.py` — each of A1–A5 gets a passing case, a failing case,
  and a not-applicable case asserting `skipped` rather than `pass`. A2 gets
  explicit coverage that `str`/`int`/`None` are never checked and that a
  fabricated `RELAY_777` fails.
- `test_week6_agreement.py` — raw agreement and Cohen's κ against hand-computed
  fixtures, including the degenerate all-PASS judge case where agreement is high
  and κ is ~0.
- `test_week6_ordering.py` — the judge aborts on uncommitted labels; `label.py`
  aborts when a run file exists; the labels sha256 recorded in the judge run
  still matches the file on disk (the anti-relabelling test).
- Case-file integrity — 25 cases, every case tagged with exactly one known mode,
  ≥2 cases with `origin.kind == "replay"`, and every replay case's parameters
  actually equal to its trace record's.

## 16. Risks and open items

- **Judge non-determinism.** Groq is not bit-deterministic even at temperature 0,
  so a re-run can shift a verdict or two. Mitigation: raw responses are recorded,
  and the write-up states that the reported agreement comes from a single
  recorded run rather than implying reproducibility it does not have. Not fixed
  by majority voting — that would triple cost and hide the variance instead of
  disclosing it.
- **25 cases is a small denominator.** One flipped verdict moves agreement by 4
  percentage points. The write-up reports the count alongside every percentage
  and avoids treating a 4-point move as signal.
- **judge_v2 overfits 25 cases.** Two few-shots drawn from these exact
  disagreements will help on these exact cases. Disclosed, with the 23-case
  secondary number in §11.
- **`deprecations.json` is hand-curated.** Unavoidable — the removals are prose,
  not symbols. Mitigated by citing a source file and line per entry, so each is
  checkable.
- **Open, from Week 5:** the predicted `_CITATION_RE` fix
  (`rag/generator.py:38`) is still unlanded. It is out of Week-6 scope per §2,
  but the Week-5 prediction remains unscored until it lands, and that should be a
  deliberate follow-up rather than a forgotten one.

## 17. Rubric traceability

| Rubric criterion | Pts | Where satisfied |
|---|---|---|
| Blind protocol: 25 labels provably predate the judge run | 25 | §8, §9 ordering guard, §14 commits C1→C2→C3 |
| Agreement before → after, iteration driven by the judge's own disagreements | 30 | §10, §11 |
| Assertion/judge split: named, implemented, removed from the prompt | 20 | §3 v0→v1 table, §6, count report in §12 |
| 2+ disagreements read, verdict on who was right, prediction honestly scored | 15 | §11 steps 2, 3, 6 |
| Eval runs in one command over 25+ mode-tagged cases incl. real regressions | 10 | §4, §12 |
