# Week 5 prediction — dated 2026-08-29

**Mode to attack next week:** "cites using full-width `【chunk: id】` brackets that
the citation checker's ASCII-only regex (`rag/generator.py::_CITATION_RE`)
never matches" — the highest-frequency real failure found in this week's
open-coding: **15% (3/20)** of the random sample and **30% (3/10)** of the
curated demo sample.

**The change:** broaden `_CITATION_RE` in `rag/generator.py` to also match the
full-width bracket form (`【chunk:\s*([^\]】\s|]+)` alongside the existing
`\[chunk:\s*([^\]\s|]+)`), so `verify_citations()` recognizes a citation
regardless of which bracket style the model used that turn. This is a
checker-side fix — it does not touch the system prompt or call the model
again, which makes it deterministically testable against already-logged
`raw_output` text with no new LLM calls.

**The exact delta expected:** re-scoring the SAME 30 already-logged
`raw_output` strings (the 20 random-sample trace_ids plus the 10 demo-sample
trace_ids from this week, listed in `notes.md`) through the broadened regex
drops the citation-format-bug mode from 15% (3/20) and 30% (3/10) to **0% in
both samples** — every one of those 6 failing traces already names a
chunk_id that is present in that trace's own `retrieved` list; the checker
was blind to it, not the model wrong about it. If re-scoring surfaces even
one of those 6 still failing, or a previously-passing trace flips to failing,
the prediction is wrong.

**What this prediction does NOT claim:** that the model will emit fewer
full-width-bracket citations going forward — this is a checker fix, not a
generation fix, and next week's rerun should track whether the *occurrence*
rate on fresh traffic changes at all (it may not, since nothing about how the
model decides to cite has changed).
