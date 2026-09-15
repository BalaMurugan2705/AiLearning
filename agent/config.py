import os

# Read from the same GROQ_MODEL env var the rest of the app uses, but with
# our own default -- rag.config.GROQ_MODEL currently has its default swapped
# with JUDGE_MODEL in an uncommitted local edit, so we deliberately don't
# import it here.
AGENT_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# USD per 1,000,000 tokens (input, output). Source: Groq's published
# on-demand rate for openai/gpt-oss-120b as of 2026-09-15 ($0.15 / $0.60).
# An unrecognized model falls back to (0.0, 0.0) so cost reports as an
# explicit $0 ("unpriced") rather than a guessed number.
PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
}


def price_for(model: str) -> tuple[float, float]:
    return PRICING_PER_MILLION_TOKENS.get(model, (0.0, 0.0))
