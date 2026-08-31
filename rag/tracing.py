"""Trace logging for the docs assistant.

Every call to RAGPipeline.ask() is appended as one JSON object per line to
TRACES_PATH. A trace records enough to replay the generation step (question,
retrieved chunk_ids + scores, prompt_version, model + params) without
re-running retrieval — retrieval itself is only replayable as long as the
underlying index hasn't changed, which is not something a trace can capture.
"""
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rag.config import BASE_DIR, GROQ_MODEL
from rag.generator import (
    PROMPT_VERSION,
    REFUSAL_MESSAGE,
    extract_citations,
    sources_from_chunks,
    verify_citations,
)

TRACES_PATH = str(Path(BASE_DIR) / "eval" / "traces.jsonl")

# Groq's chat.completions.create() is called with only model/max_tokens/messages
# (see rag/generator.py) — temperature and seed are left at the provider's
# default, so they are not fixed values this app controls or could log. That
# is a real gap: it means answer_question() is not reproducible bit-for-bit
# even when everything logged here is replayed exactly.
MODEL_PARAMS = {"max_tokens": 2048}


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def build_trace(
    *,
    trace_id: str,
    question: str,
    chunks: list[dict],
    answer: str,
    k: int,
    where: dict | None,
    rerank: bool,
    strategy: str,
    latency_ms: float,
) -> dict:
    citation_check = verify_citations(answer, chunks)
    return {
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": question,
        "strategy": strategy,
        "k": k,
        "where": where,
        "rerank": rerank,
        "prompt_version": PROMPT_VERSION,
        "model": GROQ_MODEL,
        "model_params": MODEL_PARAMS,
        "retrieved": [
            {
                "chunk_id": c.get("chunk_id"),
                "rank": c.get("rank"),
                "dense_distance": c.get("dense_distance"),
                "bm25_score": c.get("bm25_score"),
                "rrf_score": c.get("rrf_score"),
                "rerank_score": c.get("rerank_score"),
                "source_file": (c.get("metadata") or {}).get("source_file"),
                "sdk_version": (c.get("metadata") or {}).get("sdk_version"),
                "heading_path": (c.get("metadata") or {}).get("heading_path"),
            }
            for c in chunks
        ],
        "refused": answer.strip() == REFUSAL_MESSAGE,
        "citations": citation_check["cited"],
        "citation_check": citation_check,
        "sources": sources_from_chunks(chunks),
        "raw_output": answer,
        "latency_ms": round(latency_ms, 1),
    }


def append_trace(trace: dict, path: str = TRACES_PATH) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(trace, ensure_ascii=False) + "\n")


def load_traces(path: str = TRACES_PATH) -> list[dict]:
    traces = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                traces.append(json.loads(line))
    return traces


def timer() -> float:
    return time.monotonic()
