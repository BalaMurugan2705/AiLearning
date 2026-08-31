"""Requirement 1: pick one trace at random by trace_id (seeded), replay it
from the trace alone, and show replayed output next to the original.

"From the trace alone" means: the trace's question, its logged retrieved
chunk_ids + scores, its prompt_version, and its model + params -- NOT a fresh
retrieval call. The one thing a trace does NOT store is chunk text itself (see
rag/tracing.py), so replay re-fetches each chunk's text by chunk_id from the
live store. That is the honest boundary of "replayable from the trace alone"
for this app: it holds only as long as the index hasn't changed since the
trace was logged, which is precisely the kind of missing field requirement 1
asks to surface.
"""
import argparse
import random
import sys

from rag.generator import PROMPT_VERSION, answer_question
from rag.pipeline import collection_for
from rag.store import VectorStore
from rag.tracing import load_traces


def pick_trace_id(traces: list[dict], seed: int) -> str:
    ids = sorted(t["trace_id"] for t in traces)
    return random.Random(seed).choice(ids)


def replay(trace: dict) -> dict:
    strategy = trace["strategy"]
    store = VectorStore(collection_name=collection_for(strategy))

    chunks = []
    missing: list[str] = []
    for r in trace["retrieved"]:
        resolved = store.get_by_id(r["chunk_id"])
        if resolved is None:
            missing.append(r["chunk_id"])
            continue
        chunks.append(
            {
                **resolved,
                "dense_distance": r["dense_distance"],
                "bm25_score": r["bm25_score"],
                "rrf_score": r["rrf_score"],
            }
        )

    prompt_version_match = PROMPT_VERSION == trace["prompt_version"]
    replayed_answer = answer_question(
        trace["question"], chunks, max_tokens=trace["model_params"]["max_tokens"]
    )

    return {
        "trace_id": trace["trace_id"],
        "question": trace["question"],
        "original_output": trace["raw_output"],
        "replayed_output": replayed_answer,
        "identical": replayed_answer.strip() == trace["raw_output"].strip(),
        "missing_chunk_ids": missing,
        "prompt_version_current_matches_trace": prompt_version_match,
        "note": (
            "model+params, prompt_version and retrieved chunk_ids+scores all came "
            "from the trace record; chunk TEXT was re-fetched live by chunk_id "
            "(not stored in the trace) and temperature/seed were never logged "
            "because the app never sets them, so the LLM call itself is not "
            "pinned to a fixed sampling seed -- exact reproduction isn't "
            "guaranteed even with everything else identical."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=5, help="Seed for picking the trace_id")
    args = parser.parse_args()

    traces = load_traces()
    trace_id = pick_trace_id(traces, args.seed)
    trace = next(t for t in traces if t["trace_id"] == trace_id)

    result = replay(trace)
    print(f"seed={args.seed}")
    print(f"trace_id={result['trace_id']}")
    print(f"question={result['question']!r}")
    print(f"missing_chunk_ids={result['missing_chunk_ids']}")
    print(f"prompt_version_current_matches_trace={result['prompt_version_current_matches_trace']}")
    print(f"identical={result['identical']}")
    print("\n--- ORIGINAL ---\n" + result["original_output"])
    print("\n--- REPLAYED ---\n" + result["replayed_output"])
    print("\n--- NOTE ---\n" + result["note"])


if __name__ == "__main__":
    sys.exit(main())
