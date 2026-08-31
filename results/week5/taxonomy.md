# Week 5 — Taxonomy of failure modes

Random sample: 20 traces, seed `20260829`, drawn from 81 eligible traces in
`eval/traces.jsonl` (105 total traces, minus the 12 curated demo questions
and their duplicate copies — see `notes.md`). 13/20 (65%) showed no failure:
9 clean grounded+cited answers, 3 correct refusals of genuinely out-of-corpus
facts, 1 honest split of a compound question into an answered half and a
refused half. The 4 modes below are the remaining 7/20 (35%).

| Mode | Count | % of 20 | Severity | Example trace_id |
|---|---|---|---|---|
| Cites using full-width `【...】` brackets the citation checker's ASCII regex never matches | 3 | 15% | Merely annoys the reader — the prose answer is correct; only the app's own citation-verification signal silently reads it as uncited | `15f8e03f9de3` |
| Answers a version-unspecified question with only one SDK version's numbers, while the other version's chunk sat in the same retrieved set | 2 | 10% | Ships broken code to a user's repo — a reader who trusts the stated default/limit and hardcodes it against the wrong version gets a silently incorrect value | `b84fe53eb006` |
| Answers a generic "the SDK" question entirely from the unrelated second product sharing this index, with no signal that two products are indexed here | 1 | 5% | Ships broken code to a user's repo — implementing the wrong product's error-handling flow as if it were the one being asked about breaks entirely | `e7443d69a8a9` |
| Refuses a question whose four retrieved chunks look topically on-target, for a reason invisible from the trace alone | 1 | 5% | Merely annoys the reader — denies an answer rather than fabricating one | `132709d13774` |

**Total observed failure rate: 7/20 (35%).**

## Notes on naming

"Cites using full-width brackets" and "answers with one version's numbers
while the other version's chunk was retrieved" are both observations of what
happened on the page, not diagnoses — the taxonomy doesn't claim *why* the
model picked one bracket style or one SDK version over the other, only that
it did, on which traces, and how often.

Full detail — all 20 open-coded sentences, the seed and trace_id list, the
replay evidence, and the bonus demo-set comparison — is in `notes.md`.
