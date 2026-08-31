"""Requirement 2 (+ bonus): a documented, seeded random sample of 20 trace_ids
from the random pool, and (bonus) a seeded sample of 10 from the curated demo
set, kept strictly separate so neither number leaks into the other.
"""
import argparse
import random
import sys

from eval.trace_questions import DEMO
from rag.tracing import load_traces


def split_pools(traces: list[dict]) -> tuple[list[dict], list[dict]]:
    demo_qs = set(DEMO)
    demo_traces = [t for t in traces if t["question"] in demo_qs]
    random_traces = [t for t in traces if t["question"] not in demo_qs]
    return random_traces, demo_traces


def sample_ids(traces: list[dict], n: int, seed: int) -> list[str]:
    ids = sorted(t["trace_id"] for t in traces)
    return random.Random(seed).sample(ids, n)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--bonus-seed", type=int, default=20260829)
    args = parser.parse_args()

    traces = load_traces()
    random_traces, demo_traces = split_pools(traces)

    print(
        f"total traces: {len(traces)}  "
        f"random-eligible: {len(random_traces)}  demo-eligible: {len(demo_traces)}"
    )

    sample20 = sample_ids(random_traces, 20, args.seed)
    print(f"\nseed={args.seed}")
    print("RANDOM SAMPLE OF 20 trace_ids:")
    for tid in sample20:
        print(" ", tid)

    sample10 = sample_ids(demo_traces, 10, args.bonus_seed)
    print(f"\nbonus-seed={args.bonus_seed}")
    print("BONUS DEMO SAMPLE OF 10 trace_ids:")
    for tid in sample10:
        print(" ", tid)


if __name__ == "__main__":
    sys.exit(main())
