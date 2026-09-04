# judge_v1 disagreements with the 25 pre-judge labels

agreement_before: **84%** (21/25), Cohen's kappa **0.43**
Labels commit (pre-judge, verified as `judge_v1_run.json`'s own `labels_commit`): `55bc482069faaccad18a56341c45738b91df3039`

**Important disclosure carried from `eval/week6/labels_25.json`'s `labeler` field:** the 25 pre-judge labels were produced by Claude (the same assistant driving this harness), not by an independent human, at the user's explicit request after the tradeoff was raised and confirmed. Every label was produced by reading the answer and independently re-verifying its factual claims against the actual source chunks in the live vector store — not by plausibility alone — but this is a model-vs-model comparison, not a judge-vs-human validation. That distinction is real and is not softened anywhere in this write-up.

All 4 disagreements go the same direction: **human label FAIL, judge_v1 PASS.** Judge_v1's overall verdict distribution (23 PASS / 2 FAIL) is far more lenient than the human labels (19 PASS / 6 FAIL) — the judge caught 2 of the 6 real failures and missed the other 4, all 4 of them cleanly.

---

## 1. `W6-06` — mode `version-ambiguity`

**Question:** What's the max message size and how many retries does send() do by default?
**Retrieved:** `v2:client:structural:3`, `v3:client:structural:4`, `v2:client:structural:2`, `v3:streaming:structural:2`
**My label:** FAIL — "Question names no version. Answer gives ONLY v2 numbers (64 KiB max, 3 attempts) with no version qualifier at all. v3 actually allows 256 KiB and defaults to 4 attempts. A developer on v3 taking these numbers at face value gets both facts wrong."
**Judge verdict:** PASS — *"The answer correctly identifies the 64 KiB message limit and the default of 3 total attempts (1 initial + 2 retries) based on the provided v2 documentation."*

**Answer excerpt:**

> - The message body may be at most **64 KiB** in size.
> - By default, `Client.send()` makes **3 delivery attempts total**.

**Who was right:** I was right. Verified directly against `data/documents/v3/client.md`: the v3 message-size limit is **256 KiB** ("Must be valid UTF-8 and at most 256 KiB after encoding") and the v3 `retry_max_attempts` default is **4**. Both figures the answer gives are the v2 values, stated with no version qualifier anywhere. A reader working against the v3 SDK who hardcodes a 64 KiB payload cap or assumes 3 attempts is wrong on both counts.

**What this says about the prompt:** the judge's own reason names the discrepancy and dismisses it — it explicitly writes "based on the provided v2 documentation" as if that settles correctness, rather than noticing that the *question never asked about v2* and the retrieved set also contained `v3:client:structural:4`. The judge is grading **internal consistency between the answer and whatever was retrieved**, not **correctness against the actual, version-unspecified question**. It never asks "is this the full picture, or just one version's slice of it?"

---

## 2. `W6-11` — mode `cross-product-bleed`

**Question:** How do I handle errors from the SDK?
**Retrieved:** four chunks, all from `OMNUMI_SDK_IOS_DOCUMENTATION.md`
**My label:** FAIL — "Question is a generic 'the SDK' question. Answer is entirely about the unrelated Omnumi iOS SDK with zero indication that a second, unrelated product (Relay) is also indexed. A reader asking about Relay gets a completely irrelevant, unusable answer with no warning."
**Judge verdict:** PASS — *"The answer correctly distinguishes between the SDK's built-in error handling in standard mode and the manual handling required in API-Only mode, providing accurate, actionable steps for both scenarios based on the retrieved documentation."*

**Answer excerpt:**

> The Omnumi iOS SDK includes built-in error handling that presents user-friendly messages for most failures. When you use API-Only mode... inspect the API response yourself...

**Who was right:** I was right. The index holds two entirely unrelated products — the Relay SDK this whole documentation assistant exists to answer questions about, and an unrelated iOS payment SDK (Omnumi). "The SDK" in a generic question is genuinely ambiguous, and the answer commits fully to the wrong reading with no hedge, no disambiguating question, and no acknowledgment that a second product exists in this index at all.

**What this says about the prompt:** this is the most concerning miss. The judge's reason actively *praises* the answer's internal thoroughness ("correctly distinguishes... standard mode... API-Only mode... accurate, actionable steps") without ever asking the one question that matters: *is this even the product the user meant?* The judge appears to treat "the retrieved documentation" as the definition of ground truth rather than as one candidate slice of a larger, ambiguous corpus — it never reasons about what else might be indexed or whether retrieval itself might have picked the wrong product. This is the same blind spot as `W6-06`, one level up: the judge trusts retrieval instead of interrogating whether retrieval answered the actual question asked.

---

## 3. `W6-07` — mode `version-ambiguity`

**Question:** What format does a channel identifier use when sending a message?
**Retrieved:** `v2:client:structural:2`, `v2:client:structural:1`, an unrelated Omnumi chunk, `v3:client:structural:1`
**My label:** FAIL — "Answer states channel format is 'org/topic' (v2 format) with no version qualifier. v3 requires the three-segment 'org/team/topic' and its broker rejects two-segment ids with RELAY_400. A v3 developer following this answer ships a channel id their own broker will reject."
**Judge verdict:** PASS — *"The answer correctly identifies the `org/topic` format for the channel identifier as specified in the retrieved documentation for the `Client.send()` method."*

**Who was right:** I was right, and this is a genuinely dangerous case — `data/documents/v2/migrating-to-v3.md` states explicitly: *"A v2 channel `org/topic` becomes `org/team/topic` in v3, and the v3 broker rejects two-segment identifiers with `RELAY_400` rather than inferring a team."* A v3 user who formats a channel as `org/topic` per this answer gets a hard rejection from the live broker, not a silently-wrong value — this is the same identified severity as the Week 5 taxonomy's "ships broken code to a user's repo" category.

**What this says about the prompt:** identical pattern to `W6-06` — the judge again validates the answer against "what the retrieved documentation says" rather than against the actual v2/v3 discrepancy that exists in the corpus, one chunk of which (`v3:client:structural:1`) was *in the retrieved set* but contained no format detail for the judge to cross-check against.

---

## 4. `W6-12` — mode `cross-product-bleed`

**Question:** How should I handle errors in the SDK?
**Retrieved:** four chunks, all from `OMNUMI_SDK_IOS_DOCUMENTATION.md`
**My label:** FAIL — same reasoning as `W6-11`: entirely Omnumi content for a generic question, no disambiguation that two unrelated products share this index.
**Judge verdict:** PASS — *"The answer correctly synthesizes the specific error handling patterns for API-only mode and general best practices provided in the retrieved documentation, offering actionable guidance for the developer."*

**Who was right:** I was right, for the same reason as `W6-11`. This case is close to a duplicate of `W6-11` in both the question's shape and the judge's exact failure mode, which is itself informative: this is not a one-off slip, it is a **repeatable** blind spot for this specific question shape (generic "the SDK" + retrieval landing entirely on one product).

---

## Where the disagreements cluster

All 4 misses share one mechanism: **the judge validates the answer's coherence with whatever was retrieved, not the answer's correctness against the actual question** — and the question, in every miss, was ambiguous in a way the retrieved evidence quietly resolved in only one direction (one SDK version, or one of two unrelated products) without flagging it. The judge caught `W6-14` and `W6-15` cleanly, and both of those cases have the contamination *visible inside the answer itself* (Swift code next to Python parameters; an Omnumi feature name attributed to "the SDK" in a Relay-specific paragraph) — the judge can catch a contradiction it can see within one answer, but it cannot catch an answer that is internally consistent yet silently one-sided relative to a question the corpus can answer two different ways.

This directly matches the Week 5 taxonomy's two highest-severity modes (`version-ambiguity`, `cross-product-bleed`) and is exactly the blind spot DevRel's own complaint pointed at — "v2 endpoints keep getting recommended to v3 users." A judge that misses 4 of 6 real failures, and misses precisely the two modes this whole exercise exists to catch, is not safe to ship on the strength of its raw number alone.

---

## Prediction, scored

**Predicted** (committed `a067762`, before `judge_v2.txt` existed): adding `W6-06` and `W6-11` as FAIL few-shots would raise agreement from 84% (21/25) to at least 92% (23/25), specifically by flipping `W6-07` and `W6-12` to FAIL, with no other case moving.

**Actual:** agreement **84% → 72%** (21/25 → 18/25), kappa 0.43 → 0.45. Over the 23 non-few-shot cases specifically (the honest comparison, since the two few-shot cases are now near-guaranteed to agree): **91% → 70%** (21/23 → 16/23). Raw agreement *fell*, not rose — the prediction's direction was wrong, not just its magnitude.

**Where the prediction was right:** the mechanism-level diagnosis held exactly as stated. `W6-07` and `W6-12` — the two predicted flips — did flip to FAIL, and so did `W6-06` and `W6-11` themselves (trivially, since they're now literally in the prompt). All 4 of judge_v1's original misses are gone from judge_v2's disagreement list. The few-shot examples genuinely taught the judge the diagnosed blind spot: "don't just check the answer against whatever was retrieved — check whether the question could mean another version or product first."

**Where it was wrong, and why it matters more than the parts that were right:** the fix did not stay surgical. Judge_v2 generalized "check for a hidden version/product gap" into "assume there probably is one and fail on the mere absence of positive proof," producing **7 new false FAILs** on answers I had independently verified as correct and complete:

- `W6-02` (`dedupe_window_ms`) and `W6-05` (`page_size` on `Client.fetch()`) — both v3-only concepts. I confirmed directly: v2's parameter table has no `dedupe_window_ms` field at all, and v2 has no `Client.fetch()`/`page_size` concept (it used offset pagination, a different mechanism entirely, per `migrating-to-v3.md`). There is no "missing v2 value" to flag — the v3-only answer is the complete, correct answer — but judge_v2 failed both for "the retrieved documentation does not confirm the v2 limit."
- `W6-03` (`AUTH_TOKEN_EXPIRED`) is the sharpest example: judge_v2's own reason states *"v2 has no token expiry concept and thus no such error code"* — correctly identifying there is nothing to disambiguate — and then fails the answer anyway for not addressing a version-specific concept that does not exist in that version.
- `W6-08` was FAILed even though its answer explicitly says *"the v3 API provides"* cursor pagination and explicitly states *"offset pagination is no longer available"* — i.e., it already acknowledges the v2→v3 change in the way judge_v1's own instructions asked for, and judge_v2 failed it regardless.

The mechanism: the few-shots demonstrated a correct FAIL reasoned from an *evidenced* discrepancy (a real, checkable different number/format in the other version). Judge_v2 learned the surface pattern ("flag single-version/single-product answers to version/product-unspecified questions") without learning the boundary condition ("only when the other version/product genuinely differs, or genuinely exists"). It began hallucinating hypothetical discrepancies to justify a FAIL rather than checking for real ones — a more dangerous failure mode than judge_v1's leniency, because it now rejects correct, complete guidance on manufactured doubt.

**What I would try next, if iterating further:** a third few-shot showing a PASS verdict on a version-specific-but-unambiguous concept (e.g. `W6-03`'s `AUTH_TOKEN_EXPIRED` case, explicitly reasoning "v2 has no such concept, so the v3-only answer is complete") — teaching the judge the boundary condition it currently lacks, not just the trigger condition. This was not committed as `judge_v3` because the task scopes exactly one iteration; noted here as the next falsifiable step rather than acted on.
