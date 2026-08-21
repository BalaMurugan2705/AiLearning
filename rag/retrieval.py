import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")

RRF_K = 60


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def fuse_with_scores(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Merge multiple ranked id lists (best first) via Reciprocal Rank Fusion,
    returning (id, score) pairs best first.

    Note for anyone tempted to threshold on these scores: an RRF score depends
    only on rank position, never on how relevant the match actually was. The
    top hit of a perfect query and the top hit of a nonsense query score
    identically. Use the raw dense distance for confidence, not this.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)

    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    """Merge multiple ranked id lists (best first) into one ordered id list."""
    return [item for item, _ in fuse_with_scores(rankings, k)]
