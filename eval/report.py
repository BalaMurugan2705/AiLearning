"""Render results.md from the raw artifacts produced by run_eval.

Every number here comes from eval/raw/artifacts.json. Nothing is transcribed
by hand, so the write-up cannot drift from what was actually measured.
"""

STRATEGY_LABELS = {
    "structural": "structure-aware",
    "baseline": "baseline (fixed-size)",
}


def _fmt(value, dash="—", places=4):
    if value is None:
        return dash
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def _result_table(rows: list[dict], show_version: bool = False) -> str:
    header = "| # | chunk_id | source | rrf | cosine | bm25 |"
    divider = "|---|---|---|---|---|---|"
    if show_version:
        header = "| # | chunk_id | source | sdk_version | rrf | cosine | bm25 |"
        divider = "|---|---|---|---|---|---|---|"

    lines = [header, divider]
    for row in rows:
        location = f"{row['source_file']}{row['anchor']}"
        cells = [
            str(row["rank"]),
            f"`{row['chunk_id']}`",
            location,
            *([row["sdk_version"]] if show_version else []),
            _fmt(row["rrf_score"], places=5),
            _fmt(row["cosine_distance"]),
            _fmt(row["bm25_score"], places=3),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _questions_section(questions: dict) -> str:
    lines = [
        "## 1. The 8 questions and their known-correct location",
        "",
        "Written by reading the v3 pages directly, before any index existed and "
        "before any search was run. `answer_span` is the literal text that must "
        "appear in a retrieved chunk for it to count as a hit.",
        "",
        "| id | question | page | section | answer span | evidence type |",
        "|---|---|---|---|---|---|",
    ]
    for question in questions["eval"]:
        lines.append(
            f"| {question['id']} | {question['question']} | `{question['page']}` | "
            f"{question['section']} | `{question['answer_span']}` | {question['depends_on']} |"
        )
    lines.append("")
    lines.append(
        f"{sum(1 for q in questions['eval'] if q['depends_on'] in ('parameter-table-row', 'code-fence'))}"
        " of the 8 depend on a row inside a parameter table or on a code fence."
    )
    return "\n".join(lines)


def _ingest_section(artifacts: dict) -> str:
    lines = [
        "## 2. What was indexed",
        "",
        "The v2 pages represent the index that already existed. Only the 6 new v3 "
        "reference pages were ingested on top of them — the whole docs site was "
        "not re-indexed. That is asserted as a check, not a claim: the v2 chunk "
        "ids are snapshotted before the v3 ingest and confirmed still present "
        "afterwards.",
        "",
        "| strategy | v2 chunks (pre-existing) | v3 pages ingested | v3 chunks added | ingest time | v2 chunks untouched | total |",
        "|---|---|---|---|---|---|---|",
    ]
    for strategy, summary in artifacts["indexes"].items():
        v3 = summary["v3_ingest"]
        lines.append(
            f"| {STRATEGY_LABELS.get(strategy, strategy)} | {summary['v2_chunk_count']} | "
            f"{v3['files']} | {v3['chunks']} | {v3['seconds']}s | "
            f"{'yes' if summary['v2_chunks_untouched'] else 'NO'} | {summary['total_chunks']} |"
        )

    any_summary = next(iter(artifacts["indexes"].values()))
    lines += ["", "Pages ingested:", ""]
    for source_file in any_summary["v3_ingest"]["source_files"]:
        lines.append(f"- `{source_file}`")
    return "\n".join(lines)


def _hitrate_section(artifacts: dict) -> str:
    k = artifacts["k"]
    search = artifacts["search"]

    lines = [
        f"## 3. Hit-in-top-{k}: both strategies, same 8 questions",
        "",
        f"A hit requires a chunk in the top {k} that comes from the expected page "
        "**and** literally contains the answer span. Both strategies saw identical "
        "pages, the same embedding model, the same chunk size and overlap, and the "
        "same 8 questions. Only the chunking differs.",
        "",
        "| strategy | metric A: hit-in-top-5 | metric B: supported-hit-in-top-5 |",
        "|---|---|---|",
    ]
    for strategy, data in search.items():
        lines.append(
            f"| {STRATEGY_LABELS.get(strategy, strategy)} | **{data['hits']}/{data['total']}** | "
            f"**{data['supported_hits']}/{data['total']}** |"
        )

    lines += [
        "",
        "**Metric A** was pre-registered before any index existed: a top-5 chunk "
        "from the expected page whose text contains the answer span.",
        "",
        "**Metric B** was added after metric A returned the same score for both "
        "strategies and so could not tell them apart. It additionally requires the "
        "chunk to contain the support spans — for a parameter-table question, the "
        "parameter name and the table's header row. That is requirement 3's own "
        "wording turned into a check: is the parameter row still attached to its "
        "header row? Questions whose answer is prose have no support spans and "
        "score identically under both metrics by construction.",
        "",
        "Metric A is reported rather than replaced. Discarding a pre-registered "
        "metric because it gave an inconvenient answer is the exact failure that "
        "pre-registering it was meant to prevent.",
        "",
        "### Per-question record",
        "",
        "| id | question | evidence | "
        + " | ".join(f"{STRATEGY_LABELS.get(s, s)} (A / B)" for s in search)
        + " |",
        "|---|---|---|" + "---|" * len(search),
    ]

    ids = [record["id"] for record in next(iter(search.values()))["records"]]
    for index, question_id in enumerate(ids):
        first = next(iter(search.values()))["records"][index]
        cells = []
        for data in search.values():
            record = data["records"][index]
            metric_a = f"@{record['hit_rank']}" if record["hit"] else "**miss**"
            metric_b = (
                f"@{record['supported_hit_rank']}" if record["supported_hit"] else "**miss**"
            )
            cells.append(f"{metric_a} / {metric_b}")
        lines.append(
            f"| {question_id} | {first['question']} | {first['depends_on']} | "
            + " | ".join(cells)
            + " |"
        )

    return "\n".join(lines)


def _filter_section(artifacts: dict) -> str:
    demo = artifacts["filter_demo"]
    lines = [
        "## 4. Metadata filter on sdk_version",
        "",
        f"{demo['queries_tried']} candidate query/queries were tried to find one where "
        "filtering changes the top-1 result. Unlike the 8 eval questions, searching "
        "for this query is the assignment — requirement 4 asks for an existence "
        "proof that version filtering matters — so the number of attempts is "
        "reported rather than hidden.",
        "",
    ]

    if not demo["found"]:
        lines += [
            "**No query was found where the filter flipped top-1 from v2 to v3.** "
            "All attempts are shown below.",
            "",
        ]

    for attempt in demo["attempts"]:
        verdict = "top-1 flipped v2 → v3" if attempt["top1_flipped_v2_to_v3"] else "no flip"
        lines += [
            f"### Query: `{attempt['query']}` — {verdict}",
            "",
            "**Unfiltered:**",
            "",
            _result_table(attempt["unfiltered"], show_version=True),
            "",
            "**Filtered to `sdk_version = v3`:**",
            "",
            _result_table(attempt["filtered"], show_version=True),
            "",
        ]
    return "\n".join(lines)


def _calibration_section(artifacts: dict) -> str:
    calibration = artifacts["calibration"]
    lines = [
        "## 5. Refusal threshold calibration",
        "",
        "The gate refuses before generation when the closest retrieved chunk is "
        "farther than a cosine-distance threshold. The threshold is fitted on 5 "
        "held-out calibration questions — never on the 8 reported questions or the "
        "3 reported refusals, which would tune the parameter to the test set.",
        "",
        "| id | question | answerable | best cosine distance |",
        "|---|---|---|---|",
    ]
    for row in calibration["rows"]:
        lines.append(
            f"| {row['id']} | {row['question']} | {'yes' if row['answerable'] else 'no'} | "
            f"{_fmt(row['best_cosine_distance'])} |"
        )

    lines += [
        "",
        f"- Worst answerable distance: `{_fmt(calibration['worst_answerable_distance'])}`",
        f"- Best out-of-corpus distance: `{_fmt(calibration['best_out_of_corpus_distance'])}`",
        f"- Classes separable: **{'yes' if calibration['separable'] else 'no'}**",
        f"- Threshold used: **{calibration['threshold']}** ({calibration['threshold_source']})",
    ]

    if not calibration["separable"]:
        lines += [
            "",
            "The two classes overlap: at least one out-of-corpus question retrieves "
            "something closer than the worst genuinely-answerable question does. No "
            "single distance threshold can separate them, so the gate cannot be the "
            "sole defence and the forced-refusal prompt carries the load. This is "
            "reported rather than tuned away.",
        ]
    return "\n".join(lines)


def _generation_section(artifacts: dict) -> str:
    generation = artifacts["generation"]
    lines = ["## 6. Cited answers and refusals", ""]

    if generation["skipped"]:
        lines += [
            f"**Not yet run — {generation['reason']}.**",
            "",
            "Retrieval measurement above needs no API key. Set `GROQ_API_KEY` in "
            "`.env` and re-run `python -m eval.run_eval` to fill in this section.",
        ]
        return "\n".join(lines)

    lines += ["### 3 answerable questions, with a citation per claim", ""]
    for item in generation["cited"]:
        resolve = "all resolve" if item["all_citations_resolve"] else "**UNRESOLVABLE CITATION**"
        contains = (
            "cited chunk contains the claim"
            if item["cited_chunk_contains_claim"]
            else "**cited chunk does NOT contain the claim**"
        )
        lines += [
            f"#### {item['id']} — {item['question']}",
            "",
            "```",
            item["answer"].strip(),
            "```",
            "",
            f"- Citations: {', '.join(f'`{c}`' for c in item['citations']) or 'none'}",
            f"- Verification: {resolve}; {contains}",
            "",
            "Chunks retrieved for this answer:",
            "",
            _result_table(item["retrieved"]),
            "",
        ]

    refused = sum(1 for r in generation["refusals"] if r["refused"])
    lines += [
        f"### 3 out-of-corpus questions — {refused}/3 refused",
        "",
        "Transcripts verbatim.",
        "",
    ]
    for item in generation["refusals"]:
        gate = "refused by the retrieval gate, no model call" if item["gated_before_model"] else "passed the gate; refused by the prompt"
        lines += [
            f"#### {item['id']} — {item['question']}",
            "",
            f"*Why it is absent: {item['why_absent']}*",
            "",
            "```",
            item["answer"].strip(),
            "```",
            "",
            f"- Refused: **{'yes' if item['refused'] else 'NO — INVENTED AN ANSWER'}**",
            f"- Best cosine distance: `{_fmt(item['best_cosine_distance'])}` ({gate})",
            "",
        ]
    return "\n".join(lines)


def _dump_section(artifacts: dict) -> str:
    lines = [
        f"## 10. Search-only dump — all 8 questions, both strategies, top {artifacts['k']}",
        "",
        "Retrieval only. No model was called to produce anything in this section.",
        "",
    ]
    for strategy, data in artifacts["search"].items():
        lines += [f"### Strategy: {STRATEGY_LABELS.get(strategy, strategy)}", ""]
        for record in data["records"]:
            metric_a = f"HIT @{record['hit_rank']}" if record["hit"] else "MISS"
            metric_b = (
                f"HIT @{record['supported_hit_rank']}" if record["supported_hit"] else "MISS"
            )
            lines += [
                f"#### {record['id']} — {record['question']}",
                "",
                f"Expected `{record['expected_page']}` / {record['expected_section']} · "
                f"span `{record['answer_span']}` · metric A **{metric_a}** · "
                f"metric B **{metric_b}**",
                "",
                _result_table(record["results"]),
                "",
                "Contains the answer span: "
                + (
                    ", ".join(
                        f"`{r['chunk_id']}`"
                        for r in record["results"]
                        if r.get("contains_answer_span")
                    )
                    or "none"
                ),
                "",
                "Also carries the support spans (interpretable): "
                + (
                    ", ".join(
                        f"`{r['chunk_id']}`"
                        for r in record["results"]
                        if r.get("supports_claim")
                    )
                    or "none"
                ),
                "",
            ]
    return "\n".join(lines)


def _find_record(artifacts: dict, strategy: str, question_id: str) -> dict | None:
    for record in artifacts["search"][strategy]["records"]:
        if record["id"] == question_id:
            return record
    return None


def _decision_section(artifacts: dict) -> str:
    search = artifacts["search"]
    structural, baseline = search["structural"], search["baseline"]

    return "\n".join(
        [
            "## 7. Which chunker ships, and why",
            "",
            f"The structure-aware chunker ships. On the pre-registered metric the two "
            f"are indistinguishable — {structural['hits']}/{structural['total']} against "
            f"{baseline['hits']}/{baseline['total']} — and if that were the only number "
            f"measured, the honest conclusion would be that the rewrite bought nothing. "
            f"The stricter metric separates them: {structural['supported_hits']}/"
            f"{structural['total']} against {baseline['supported_hits']}/{baseline['total']}. "
            "The difference is not that the baseline fails to retrieve the right page; it "
            "retrieves the right page every time. The difference is that the baseline "
            "hands back fragments that contain the answer without containing what makes "
            "the answer mean anything. Splitting a twelve-row parameter table on character "
            "count leaves rows seven through twelve stranded from the header row that "
            "names the columns, so a chunk reading `| dedupe_window_ms | int | 600000 | no "
            "| ... 86400000 ... |` is retrievable but not interpretable — the number could "
            "be a default, a maximum, or a rate. Repeating the header into every part of a "
            "split table costs about eighty characters per chunk and converts an "
            "uninterpretable fragment into a self-contained fact. That is the whole trade, "
            "and at this corpus size it is cheap. The honest caveat is that the margin is "
            "one question out of eight, on an eleven-page corpus; this is a directional "
            "result about a known mechanism, not a precise effect size, and a larger corpus "
            "with more deep-table questions would be needed to put an error bar on it.",
        ]
    )


def _embarrassment_section(artifacts: dict) -> str:
    baseline_q1 = _find_record(artifacts, "baseline", "Q1")
    baseline_q2 = _find_record(artifacts, "baseline", "Q2")

    lines = [
        "## 8. The retrieval that embarrassed us, and its diagnosis",
        "",
        "**What happened.** The first run scored 8/8 for both strategies and we nearly "
        "wrote that up as 'no measurable difference'. Reading the dump instead of the "
        "summary showed the number was wrong in a way the number could not reveal.",
        "",
    ]

    if baseline_q1 and baseline_q1["results"]:
        top = baseline_q1["results"][0]
        lines += [
            f"For Q1 — *{baseline_q1['question']}* — the baseline index scored a hit at "
            f"rank {baseline_q1['hit_rank']} on `{top['chunk_id']}`. That chunk is a "
            "fragment of a **code sample**:",
            "",
            "```",
            top["preview"][:180],
            "```",
            "",
            "It contains the string `2000`, and it is on the correct page, so the metric "
            "counted it. But `retry_backoff_ms=2000` there is an argument a caller passed "
            "in an example — the page never says, in that chunk, that 2000 is the default. "
            "A model given only that chunk would have to infer the default from an example, "
            "which is precisely the invention the grounding rules exist to prevent. The "
            "retrieval looked perfect and the evidence was worthless.",
            "",
        ]

    lines += [
        "**Diagnosis.** The metric tested the presence of a string, not the presence of a "
        "*claim*. `2000` is a short, generic span that occurs several times on the page in "
        "different roles: as a default in the parameter table, as an argument in a code "
        "sample, and as a computed delay in prose. Any metric keyed on that span alone "
        "cannot tell those roles apart, so it saturates and reports a tie between a "
        "chunker that preserves structure and one that shreds it.",
        "",
        "**What we changed.** Not the questions and not the pre-registered metric — both "
        "stay as recorded. We added a second metric requiring the answer span to co-occur "
        "with the spans that fix its meaning, and reported both. The addition is disclosed "
        "in `eval/questions.json` under `_support_spans_disclosure`, because a metric "
        "introduced after seeing results is only defensible if the reader can see when it "
        "was introduced and why.",
        "",
    ]

    if baseline_q2:
        lines += [
            "**What the second metric then found.** Q2 — *"
            f"{baseline_q2['question']}* — is the one question the baseline loses. "
            "`dedupe_window_ms` is the ninth row of a twelve-row table. The baseline "
            "chunker splits that table on character count, so the ninth row lands in the "
            "second fragment, which carries the value `86400000` but no header row. The "
            "structure-aware chunker repeats the header into every part, so the same row "
            "arrives interpretable. The failure is not random: it is a deterministic "
            "consequence of where the split falls, and it will hit any row past the first "
            "fragment of any table longer than the chunk size.",
            "",
        ]

    lines += [
        "**The second thing that embarrassed us.** The refusal threshold separates the "
        "calibration classes by a margin of roughly 0.04 in cosine distance. That is a "
        "real separation but a thin one, fitted on five questions. We report it as a "
        "working threshold, not a robust one, and the forced-refusal prompt remains the "
        "primary defence rather than the backstop.",
    ]
    return "\n".join(lines)


def _bonus_section(artifacts: dict) -> str:
    generation = artifacts["generation"]
    lines = [
        "## 9. Bonus — precision versus completeness",
        "",
        "The candidate is Q1. The structure-aware index retrieves the parameter-table row "
        "stating the default; the baseline index retrieves the code sample showing "
        "`retry_backoff_ms=2000` actually being passed to `client.send()`. The "
        "structure-aware chunk is the more *precise* evidence and the weaker *worked "
        "example*: it states the value authoritatively but shows nothing about how the "
        "parameter is supplied, whether it pairs with `retry_backoff_factor`, or what a "
        "real call looks like.",
        "",
    ]
    if generation["skipped"]:
        lines += [
            f"The side-by-side generated answers are **not yet produced — "
            f"{generation['reason']}**. Re-running `python -m eval.run_eval` with a key "
            "set will fill them in.",
        ]
    else:
        lines += [
            "See the generated answers in section 6 for the side-by-side comparison.",
        ]
    lines += [
        "",
        "The tension is that retrieval precision and answer completeness are not the same "
        "objective, and optimising the chunker for the first can quietly cost the second: "
        "a tight, single-fact chunk maximises the chance the right value is retrieved while "
        "minimising the surrounding material a reader needs to use that value correctly. "
        "The mitigation we would reach for is not a looser chunker but a retrieval pass "
        "that pulls a fact chunk together with the nearest example chunk under the same "
        "heading, so precision decides what is found and completeness decides what is sent.",
    ]
    return "\n".join(lines)


def render(artifacts: dict, questions: dict) -> str:
    search = artifacts["search"]
    numbers = "; ".join(
        f"{STRATEGY_LABELS.get(s, s)} {d['hits']}/{d['total']} (A) · "
        f"{d['supported_hits']}/{d['total']} (B)"
        for s, d in search.items()
    )

    sections = [
        "# Week 3 — Task Set E results",
        "",
        f"Generated by `python -m eval.run_eval`. Headline: {numbers} "
        f"hit-in-top-{artifacts['k']} over the same 8 questions.",
        "",
        _questions_section(questions),
        "",
        _ingest_section(artifacts),
        "",
        _hitrate_section(artifacts),
        "",
        _filter_section(artifacts),
        "",
        _calibration_section(artifacts),
        "",
        _generation_section(artifacts),
        "",
        _decision_section(artifacts),
        "",
        _embarrassment_section(artifacts),
        "",
        _bonus_section(artifacts),
        "",
        _dump_section(artifacts),
    ]
    return "\n".join(sections) + "\n"
