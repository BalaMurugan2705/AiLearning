import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")

RRF_K = 60


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    """Merge multiple ranked id lists (best first) into one, via Reciprocal
    Rank Fusion: score(id) = sum(1 / (k + rank)) across every ranking it
    appears in. An id present in only one ranking is still included."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)

    return sorted(scores, key=lambda item: scores[item], reverse=True)
