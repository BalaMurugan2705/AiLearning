"""Populate eval/traces.jsonl by running a week's worth of realistic
questions through the production pipeline configuration (structural chunker,
no rerank, no sdk_version filter -- exactly what app.py uses).

Usage:
    python -m eval.generate_traces          # random pool only
    python -m eval.generate_traces --demo    # curated demo/DX-review set only
    python -m eval.generate_traces --all     # both
"""
import argparse
import sys
import time

from eval.trace_questions import DEMO, RANDOM_POOL
from rag.pipeline import RAGPipeline


def run(pipeline: RAGPipeline, questions: list[str], label: str) -> None:
    for i, question in enumerate(questions, 1):
        for attempt in range(3):
            try:
                result = pipeline.ask(question)
                break
            except Exception as exc:  # rate limits / transient network errors
                if attempt == 2:
                    print(f"  [{label} {i}/{len(questions)}] FAILED: {question!r} -> {exc}")
                    result = None
                    break
                time.sleep(2 * (attempt + 1))
        if result is not None:
            print(f"  [{label} {i}/{len(questions)}] {result['trace_id']}  {question}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Only run the curated demo set")
    parser.add_argument("--all", action="store_true", help="Run both pools")
    args = parser.parse_args()

    pipeline = RAGPipeline()  # defaults: strategy=structural, no filter, no rerank
    print(f"Index has {pipeline.document_count()} chunks under strategy '{pipeline.strategy}'.")

    if args.demo:
        run(pipeline, DEMO, "demo")
    elif args.all:
        run(pipeline, RANDOM_POOL, "random")
        run(pipeline, DEMO, "demo")
    else:
        run(pipeline, RANDOM_POOL, "random")


if __name__ == "__main__":
    sys.exit(main())
