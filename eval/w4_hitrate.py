"""Week 4 Task Set E — hit-rate@3 measurement harness.

Runs the 12-question golden set (eval/golden_set.jsonl) through the current
retriever and records, per question: whether the known-correct chunk_id
appeared in the top 3, at what rank, and how long the query took. This is
the "before" measurement — written to eval/raw/w4_baseline.json and never
edited by hand.

Uses its own collection (not the app's "docs_structural") so running this
never touches whatever is really indexed for the running app.
"""
import json
import time
from pathlib import Path

from rag.chunking import STRUCTURAL
from rag.pipeline import RAGPipeline
from rag.store import VectorStore

BASE = Path(__file__).resolve().parent
REPO = BASE.parent
K = 3
EVAL_COLLECTION = "w4_eval_structural"


def load_golden_set() -> list[dict]:
    with (BASE / "golden_set.jsonl").open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_index() -> RAGPipeline:
    store = VectorStore(collection_name=EVAL_COLLECTION)
    pipeline = RAGPipeline(store=store, strategy=STRUCTURAL, require_front_matter=True)
    pipeline.reset()
    pipeline.ingest_path(str(REPO / "data/documents/v2"))
    pipeline.ingest_path(str(REPO / "data/documents/v3"))
    return pipeline


def median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def run(pipeline: RAGPipeline, questions: list[dict], rerank: bool = False) -> list[dict]:
    rows = []
    for q in questions:
        started = time.perf_counter()
        results = pipeline.retrieve(q["question"], k=K, rerank=rerank)
        elapsed_ms = (time.perf_counter() - started) * 1000

        rank = None
        for r in results:
            if r["chunk_id"] == q["chunk_id"]:
                rank = r["rank"] + 1
                break

        rows.append(
            {
                "id": q["id"],
                "question": q["question"],
                "expected_chunk_id": q["chunk_id"],
                "answer_span": q["answer_span"],
                "evidence_type": q["evidence_type"],
                "hit": rank is not None,
                "hit_rank": rank,
                "latency_ms": round(elapsed_ms, 2),
                "retrieved": [
                    {
                        "rank": r["rank"] + 1,
                        "chunk_id": r["chunk_id"],
                        "rrf_score": round(r["rrf_score"], 6),
                        "cosine_distance": (
                            None if r["dense_distance"] is None else round(r["dense_distance"], 4)
                        ),
                        "bm25_score": (
                            None if r["bm25_score"] is None else round(r["bm25_score"], 3)
                        ),
                        "contains_answer_span": q["answer_span"] in r["text"],
                        "preview": " ".join(r["text"].split())[:200],
                    }
                    for r in results
                ],
            }
        )
    return rows


def score_and_report(pipeline: RAGPipeline, questions: list[dict], rerank: bool, label: str) -> dict:
    rows = run(pipeline, questions, rerank=rerank)

    hits = sum(1 for r in rows if r["hit"])
    hit_rate = hits / len(rows)
    p50 = median([r["latency_ms"] for r in rows])

    print(f"\n=== {label} (rerank={rerank}) ===")
    print(f"hit-rate@{K}: {hits}/{len(rows)} = {hit_rate:.2f}")
    print(f"p50 latency per query: {p50:.1f} ms")
    for r in rows:
        mark = "HIT " if r["hit"] else "MISS"
        rank = f"@{r['hit_rank']}" if r["hit"] else ""
        print(f"  {r['id']:>3} [{mark}{rank:<3}] {r['question']}")

    return {
        "k": K,
        "rerank": rerank,
        "hits": hits,
        "total": len(rows),
        "hit_rate": hit_rate,
        "p50_latency_ms": round(p50, 2),
        "rows": rows,
    }


def main() -> None:
    questions = load_golden_set()
    pipeline = build_index()

    (BASE / "raw").mkdir(parents=True, exist_ok=True)

    baseline = score_and_report(pipeline, questions, rerank=False, label="BEFORE (hybrid RRF only)")
    (BASE / "raw" / "w4_baseline.json").write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    after = score_and_report(pipeline, questions, rerank=True, label="AFTER (+ cross-encoder rerank top-25)")
    (BASE / "raw" / "w4_after.json").write_text(
        json.dumps(after, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n=== Summary ===")
    print(f"hit-rate@{K}: {baseline['hit_rate']:.2f} -> {after['hit_rate']:.2f}")
    print(f"p50 latency: {baseline['p50_latency_ms']:.1f}ms -> {after['p50_latency_ms']:.1f}ms")
    print(f"\nWrote {BASE / 'raw' / 'w4_baseline.json'}")
    print(f"Wrote {BASE / 'raw' / 'w4_after.json'}")


if __name__ == "__main__":
    main()
