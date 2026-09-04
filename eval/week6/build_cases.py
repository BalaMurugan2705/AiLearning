"""The 25-case eval set: five cases per Week 5 failure mode.

Regression cases are lifted from eval/traces.jsonl by --from-trace rather than
retyped. A hand-retyped question is a paraphrase of a failure someone
remembers; a lifted one is the failure that actually happened, with the same
k, where, strategy, rerank, model and params it happened under.
"""
import argparse
import json
from pathlib import Path

from rag.tracing import load_traces

BASE = Path(__file__).resolve().parent
CASES_PATH = BASE / "cases.jsonl"

# Verbatim from results/week5/taxonomy.md, plus "clean" for the cases expected
# to pass. Renaming any of these would break the link between the two weeks.
MODES = (
    "citation-format",
    "version-ambiguity",
    "cross-product-bleed",
    "unexplained-refusal",
    "clean",
)


def case_from_trace(
    trace: dict, case_id: str, mode: str, version_sensitive: bool, notes: str
) -> dict:
    return {
        "case_id": case_id,
        "question": trace["question"],
        "mode": mode,
        "origin": {"kind": "replay", "trace_id": trace["trace_id"]},
        "version_sensitive": version_sensitive,
        "sdk_version_intent": "unspecified",
        "retrieval": {
            "k": trace["k"],
            "where": trace["where"],
            "strategy": trace["strategy"],
            "rerank": trace["rerank"],
        },
        "generation": {"model": trace["model"], "model_params": trace["model_params"]},
        # The full logged records, not just the ids. rag.generator.should_refuse
        # treats a chunk with no dense_distance as no evidence and refuses, so
        # dropping the scores here would make every replay case answer with the
        # refusal string instead of reproducing its failure. eval/replay.py does
        # the same thing for the same reason.
        "replay_retrieved": [
            {
                "chunk_id": r["chunk_id"],
                "dense_distance": r["dense_distance"],
                "bm25_score": r["bm25_score"],
                "rrf_score": r["rrf_score"],
                "rerank_score": r.get("rerank_score"),
            }
            for r in trace["retrieved"]
        ],
        "notes": notes,
    }


def load_cases(path: Path | None = None) -> list[dict]:
    path = path or CASES_PATH
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-trace", required=True, help="trace_id to lift a case from")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--version-sensitive", action="store_true")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    trace = next(t for t in load_traces() if t["trace_id"] == args.from_trace)
    case = case_from_trace(
        trace, args.case_id, args.mode, args.version_sensitive, args.notes
    )
    print(json.dumps(case, ensure_ascii=False))


if __name__ == "__main__":
    main()
