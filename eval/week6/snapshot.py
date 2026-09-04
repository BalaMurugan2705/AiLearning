"""Generates the frozen 25-answer set that everything downstream scores.

Run once, deliberately. The one-command eval re-scores this file and never
regenerates it: the 25 hand labels describe THIS text, and the whole
agreement_before -> agreement_after comparison is only attributable to the
judge prompt if the answers underneath it hold still.

Replay cases resolve their chunks by chunk_id from the store using the scores
their trace logged (the same boundary eval/replay.py documents -- a trace
stores chunk ids, not chunk text). Authored cases retrieve live.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.week6.build_cases import load_cases
from rag.config import REFUSAL_MESSAGE
from rag.generator import PROMPT_VERSION, answer_question, extract_citations, verify_citations
from rag.pipeline import RAGPipeline, collection_for
from rag.store import VectorStore

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
SNAPSHOT_PATH = REPO / "eval" / "raw" / "answers_25.json"


def canonical_sha256(obj) -> str:
    """Hash of a JSON value, insensitive to key order."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def resolve_chunks(case: dict) -> list[dict]:
    """The chunks this case's answer is generated from.

    Replay cases rebuild the exact retrieved set the trace logged, so the
    answer is produced from the same evidence as the original failure.
    """
    strategy = case["retrieval"]["strategy"]
    if case["origin"]["kind"] == "replay":
        store = VectorStore(collection_name=collection_for(strategy))
        chunks = []
        for rank, record in enumerate(case["replay_retrieved"]):
            resolved = store.get_by_id(record["chunk_id"])
            if resolved is None:
                continue
            # The trace's own scores are reattached, not recomputed. Leaving
            # dense_distance as None would trip should_refuse(), which treats a
            # chunk carrying no dense distance as no evidence -- every replay
            # case would return the refusal string and reproduce nothing.
            chunks.append(
                {
                    **resolved,
                    "rank": rank,
                    "dense_distance": record["dense_distance"],
                    "bm25_score": record["bm25_score"],
                    "rrf_score": record["rrf_score"],
                    "rerank_score": record.get("rerank_score"),
                }
            )
        return chunks

    pipeline = RAGPipeline(strategy=strategy)
    return pipeline.retrieve(
        case["question"],
        k=case["retrieval"]["k"],
        where=case["retrieval"]["where"],
        rerank=case["retrieval"]["rerank"],
    )


def _call_answer(question: str, chunks: list[dict], max_tokens: int, model: str) -> str:
    return answer_question(question, chunks, max_tokens=max_tokens, model=model)


def build_snapshot(cases: list[dict], resolve_fn=resolve_chunks, answer_fn=_call_answer) -> dict:
    answers = []
    for case in cases:
        chunks = resolve_fn(case)
        started = time.monotonic()
        raw_output = answer_fn(
            case["question"],
            chunks,
            case["generation"]["model_params"]["max_tokens"],
            case["generation"]["model"],
        )
        latency_ms = (time.monotonic() - started) * 1000
        citation_check = verify_citations(raw_output, chunks)

        answers.append(
            {
                "case_id": case["case_id"],
                "question": case["question"],
                "mode": case["mode"],
                "version_sensitive": case["version_sensitive"],
                "sdk_version_intent": case["sdk_version_intent"],
                "origin": case["origin"],
                "retrieved": [
                    {
                        "chunk_id": c.get("chunk_id"),
                        "rank": c.get("rank"),
                        "dense_distance": c.get("dense_distance"),
                        "bm25_score": c.get("bm25_score"),
                        "rrf_score": c.get("rrf_score"),
                        "source_file": (c.get("metadata") or {}).get("source_file"),
                        "sdk_version": (c.get("metadata") or {}).get("sdk_version"),
                        "heading_path": (c.get("metadata") or {}).get("heading_path"),
                        "text": c.get("text", ""),
                    }
                    for c in chunks
                ],
                "raw_output": raw_output,
                "refused": raw_output.strip() == REFUSAL_MESSAGE,
                "citations": extract_citations(raw_output),
                "citation_check": citation_check,
                "prompt_version": PROMPT_VERSION,
                "model": case["generation"]["model"],
                "model_params": case["generation"]["model_params"],
                "latency_ms": round(latency_ms, 1),
                "answer_sha256": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "eval/week6/snapshot.py",
        "answers_sha256": canonical_sha256(answers),
        "answers": answers,
    }


def load_snapshot(path: Path | None = None) -> dict:
    return json.loads((path or SNAPSHOT_PATH).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--i-know-this-invalidates-labels",
        action="store_true",
        help="required to overwrite a snapshot once labels exist",
    )
    args = parser.parse_args()

    labels = BASE / "labels_25.json"
    if SNAPSHOT_PATH.exists() and labels.exists() and not args.i_know_this_invalidates_labels:
        raise SystemExit(
            f"{SNAPSHOT_PATH} already exists and {labels} was written against it.\n"
            "Regenerating would silently invalidate all 25 hand labels. Pass "
            "--i-know-this-invalidates-labels only if you intend to relabel from scratch."
        )

    snapshot = build_snapshot(load_cases())
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    refusals = sum(1 for a in snapshot["answers"] if a["refused"])
    print(f"wrote {SNAPSHOT_PATH}")
    print(f"answers: {len(snapshot['answers'])}  refusals: {refusals}")
    print(f"answers_sha256: {snapshot['answers_sha256']}")


if __name__ == "__main__":
    main()
