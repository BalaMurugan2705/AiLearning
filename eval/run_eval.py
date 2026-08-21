"""Week 3 evaluation harness — produces every number in results.md.

One command, all artifacts. Nothing in results.md is typed by hand, so the
write-up and the JSON on disk cannot disagree with each other.

    python -m eval.run_eval

Retrieval measurement needs no API key. Generation (3 cited answers, 3
refusals) is skipped with a notice when GROQ_API_KEY is unset, and filled in
on a later run once it is.
"""
import json
import time
from pathlib import Path

from rag.chunking import BASELINE, STRUCTURAL
from rag.config import GROQ_API_KEY, REFUSAL_DISTANCE_THRESHOLD, REFUSAL_MESSAGE
from eval.metrics import score_question
from rag.generator import answer_question, verify_citations
from rag.pipeline import RAGPipeline

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw"
REPO = BASE.parent

# Pinned here rather than read from TOP_K: a measurement harness should not
# inherit a parameter that someone can later change for the web UI and
# silently invalidate every recorded number.
K = 5

V2_DIR = "data/documents/v2"
V3_DIR = "data/documents/v3"

# Candidate queries for the sdk_version filter demonstration. Unlike the 8
# eval questions, searching these until one exhibits the bug IS the assignment
# — requirement 4 asks for an existence proof. How many were tried is recorded
# and reported, so the search is visible rather than hidden.
FILTER_CANDIDATES = [
    "default retry backoff for Client.send()",
    "what is the default retry_backoff_ms value",
    "how long does Client.send() wait before the first retry",
    "retry backoff default",
]

# Three of the eight, chosen to span the evidence types: a parameter-table
# row, a prose sentence, and a code fence.
GENERATION_IDS = ("Q1", "Q4", "Q7")


def load_questions() -> dict:
    return json.loads((BASE / "questions.json").read_text(encoding="utf-8"))


def build_index(strategy: str) -> tuple[RAGPipeline, dict]:
    """Seed the v2 pages (the 'already indexed' state), then ingest ONLY the 6
    new v3 reference pages, and prove the v2 chunks were left alone."""
    pipeline = RAGPipeline(strategy=strategy, require_front_matter=True)
    pipeline.reset()

    seed = pipeline.ingest_path(str(REPO / V2_DIR))
    v2_ids = pipeline.store.all_ids()

    started = time.perf_counter()
    new = pipeline.ingest_path(str(REPO / V3_DIR))
    elapsed = time.perf_counter() - started

    after_ids = pipeline.store.all_ids()

    return pipeline, {
        "strategy": strategy,
        "v2_seed": {"files": seed["files_ingested"], "chunks": seed["chunks_ingested"]},
        "v3_ingest": {
            "files": new["files_ingested"],
            "chunks": new["chunks_ingested"],
            "source_files": sorted(new["source_files"]),
            "seconds": round(elapsed, 2),
        },
        "v2_chunks_untouched": v2_ids <= after_ids,
        "v2_chunk_count": len(v2_ids),
        "total_chunks": len(after_ids),
    }


def _serialize(result: dict, answer_span: str | None = None) -> dict:
    metadata = result["metadata"]
    row = {
        "rank": result["rank"] + 1,
        "chunk_id": result["chunk_id"],
        "source_file": metadata.get("source_file", ""),
        "anchor": metadata.get("anchor", ""),
        "heading_path": metadata.get("heading_path", ""),
        "sdk_version": metadata.get("sdk_version", ""),
        "rrf_score": round(result["rrf_score"], 6),
        "cosine_distance": (
            None if result["dense_distance"] is None else round(result["dense_distance"], 4)
        ),
        "bm25_score": (
            None if result["bm25_score"] is None else round(result["bm25_score"], 3)
        ),
        "preview": " ".join(result["text"].split())[:220],
    }
    if answer_span is not None:
        row["contains_answer_span"] = answer_span in result["text"]
    return row


def run_questions(pipeline: RAGPipeline, questions: list[dict]) -> list[dict]:
    """Search-only, scored under both metrics. See eval/metrics.py."""
    records = []
    for question in questions:
        results = pipeline.retrieve(question["question"], k=K)
        score = score_question(results, question)

        rows = [_serialize(r, question["answer_span"]) for r in results]
        for row, result in zip(rows, results):
            row["supports_claim"] = all(
                span in result["text"] for span in question.get("support_spans", [])
            ) and row["contains_answer_span"]

        records.append(
            {
                "id": question["id"],
                "question": question["question"],
                "expected_page": question["page"],
                "expected_section": question["section"],
                "answer_span": question["answer_span"],
                "support_spans": question.get("support_spans", []),
                "depends_on": question["depends_on"],
                **score,
                "results": rows,
            }
        )
    return records


def run_filter_demo(pipeline: RAGPipeline) -> dict:
    attempts = []
    for query in FILTER_CANDIDATES:
        unfiltered = pipeline.retrieve(query, k=K)
        filtered = pipeline.retrieve(query, k=K, where={"sdk_version": "v3"})

        flipped = bool(
            unfiltered
            and filtered
            and unfiltered[0]["chunk_id"] != filtered[0]["chunk_id"]
            and unfiltered[0]["metadata"].get("sdk_version") == "v2"
            and filtered[0]["metadata"].get("sdk_version") == "v3"
        )
        attempts.append(
            {
                "query": query,
                "top1_flipped_v2_to_v3": flipped,
                "unfiltered": [_serialize(r) for r in unfiltered],
                "filtered": [_serialize(r) for r in filtered],
            }
        )
        if flipped:
            break

    return {
        "queries_tried": len(attempts),
        "found": any(a["top1_flipped_v2_to_v3"] for a in attempts),
        "attempts": attempts,
    }


def calibrate_threshold(pipeline: RAGPipeline, calibration: list[dict]) -> dict:
    """Fit the refusal threshold on held-out calibration questions only.

    Fitting it on the 8 reported questions plus the 3 reported refusals would
    tune the parameter to the test set and make the reported outcome
    optimistic by construction.
    """
    rows = []
    for question in calibration:
        results = pipeline.retrieve(question["question"], k=K)
        distances = [r["dense_distance"] for r in results if r["dense_distance"] is not None]
        rows.append(
            {
                "id": question["id"],
                "question": question["question"],
                "answerable": question["answerable"],
                "best_cosine_distance": round(min(distances), 4) if distances else None,
                "top1_chunk_id": results[0]["chunk_id"] if results else None,
            }
        )

    answerable = [r["best_cosine_distance"] for r in rows if r["answerable"] and r["best_cosine_distance"] is not None]
    out_of_corpus = [r["best_cosine_distance"] for r in rows if not r["answerable"] and r["best_cosine_distance"] is not None]

    worst_answerable = max(answerable) if answerable else None
    best_oov = min(out_of_corpus) if out_of_corpus else None
    separable = (
        worst_answerable is not None and best_oov is not None and worst_answerable < best_oov
    )

    threshold = (
        round((worst_answerable + best_oov) / 2, 4) if separable else REFUSAL_DISTANCE_THRESHOLD
    )

    return {
        "rows": rows,
        "worst_answerable_distance": worst_answerable,
        "best_out_of_corpus_distance": best_oov,
        "separable": separable,
        "threshold": threshold,
        "threshold_source": "calibrated" if separable else "config default (classes overlap)",
    }


def run_generation(
    pipeline: RAGPipeline, questions: list[dict], out_of_corpus: list[dict], threshold: float
) -> dict:
    if not GROQ_API_KEY:
        return {"skipped": True, "reason": "GROQ_API_KEY is not set"}

    by_id = {q["id"]: q for q in questions}

    cited = []
    for question_id in GENERATION_IDS:
        question = by_id[question_id]
        results = pipeline.retrieve(question["question"], k=K)
        answer = answer_question(question["question"], results, threshold=threshold)
        report = verify_citations(answer, results, expected_span=question["answer_span"])
        cited.append(
            {
                "id": question_id,
                "question": question["question"],
                "answer": answer,
                "answer_span": question["answer_span"],
                "citations": report["cited"],
                "unresolvable": report["unresolvable"],
                "all_citations_resolve": report["ok"],
                "cited_chunk_contains_claim": report.get("span_supported"),
                "retrieved": [_serialize(r, question["answer_span"]) for r in results],
            }
        )

    refusals = []
    for question in out_of_corpus:
        results = pipeline.retrieve(question["question"], k=K)
        best = [r["dense_distance"] for r in results if r["dense_distance"] is not None]
        answer = answer_question(question["question"], results, threshold=threshold)
        refusals.append(
            {
                "id": question["id"],
                "question": question["question"],
                "why_absent": question["why_absent"],
                "answer": answer,
                "refused": answer.strip() == REFUSAL_MESSAGE,
                "gated_before_model": bool(best) and min(best) > threshold,
                "best_cosine_distance": round(min(best), 4) if best else None,
                "top_chunk_ids": [r["chunk_id"] for r in results],
            }
        )

    return {"skipped": False, "cited": cited, "refusals": refusals}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    questions = load_questions()

    artifacts: dict = {"k": K, "indexes": {}, "search": {}}

    pipelines = {}
    for strategy in (STRUCTURAL, BASELINE):
        print(f"[build] {strategy} ...")
        pipeline, summary = build_index(strategy)
        pipelines[strategy] = pipeline
        artifacts["indexes"][strategy] = summary
        print(
            f"    v2 seed: {summary['v2_seed']['chunks']} chunks | "
            f"v3 ingest: {summary['v3_ingest']['chunks']} chunks "
            f"in {summary['v3_ingest']['seconds']}s | "
            f"v2 untouched: {summary['v2_chunks_untouched']}"
        )

    for strategy, pipeline in pipelines.items():
        print(f"[search] {strategy} ...")
        records = run_questions(pipeline, questions["eval"])
        hits = sum(1 for r in records if r["hit"])
        supported = sum(1 for r in records if r["supported_hit"])
        artifacts["search"][strategy] = {
            "hits": hits,
            "supported_hits": supported,
            "total": len(records),
            "records": records,
        }
        print(
            f"    metric A hit-in-top-{K}: {hits}/{len(records)}   "
            f"metric B supported-hit: {supported}/{len(records)}"
        )

    print("[filter] searching for a query where sdk_version changes top-1 ...")
    artifacts["filter_demo"] = run_filter_demo(pipelines[STRUCTURAL])
    print(
        f"    tried {artifacts['filter_demo']['queries_tried']} "
        f"query/queries, found: {artifacts['filter_demo']['found']}"
    )

    print("[calibrate] fitting refusal threshold on held-out questions ...")
    calibration = calibrate_threshold(pipelines[STRUCTURAL], questions["calibration"])
    artifacts["calibration"] = calibration
    print(
        f"    worst answerable={calibration['worst_answerable_distance']} "
        f"best out-of-corpus={calibration['best_out_of_corpus_distance']} "
        f"separable={calibration['separable']} threshold={calibration['threshold']}"
    )

    print("[generate] 3 cited answers + 3 refusals ...")
    artifacts["generation"] = run_generation(
        pipelines[STRUCTURAL], questions["eval"], questions["out_of_corpus"], calibration["threshold"]
    )
    if artifacts["generation"]["skipped"]:
        print(f"    SKIPPED: {artifacts['generation']['reason']}")
    else:
        refused = sum(1 for r in artifacts["generation"]["refusals"] if r["refused"])
        print(f"    refused {refused}/3 out-of-corpus questions")

    (RAW / "artifacts.json").write_text(
        json.dumps(artifacts, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nWrote {RAW / 'artifacts.json'}")

    from eval.report import render

    output = REPO / "results.md"
    output.write_text(render(artifacts, questions), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
