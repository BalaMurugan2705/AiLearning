from sentence_transformers import CrossEncoder

from rag.config import RERANK_MODEL


class CrossEncoderReranker:
    """Reorders a candidate list by how well each chunk actually answers the
    query, rather than by keyword/embedding overlap.

    The dense and BM25 legs used upstream are bi-encoders: query and chunk are
    scored independently, which is what makes them cheap enough to run over
    an entire corpus. A cross-encoder feeds the query and one candidate into
    the model together, so it can judge relevance directly instead of via a
    similarity shortcut — at the cost of one model call per candidate, which
    is why it only ever runs over a short list handed to it by cheaper
    retrieval first.
    """

    def __init__(self, model_name: str = RERANK_MODEL):
        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        if not candidates:
            return []

        # The chunk text alone doesn't say which SDK version or page it came
        # from, so a confidently-worded wrong-version chunk can out-score a
        # correct-version one on meaning alone. Prepending that context is
        # part of feeding the cross-encoder properly — not a second retrieval
        # mechanism — the same way passage rerankers are commonly given a
        # title alongside the passage.
        pairs = [(query, _contextualize(c)) for c in candidates]
        scores = self._model.predict(pairs)

        ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)[:top_k]

        return [
            {**candidate, "rerank_score": float(score), "rank": rank}
            for rank, (candidate, score) in enumerate(ranked)
        ]


def _contextualize(candidate: dict) -> str:
    metadata = candidate.get("metadata") or {}
    source = metadata.get("source_file", "")
    version = metadata.get("sdk_version", "")
    heading = metadata.get("heading_path", "")
    prefix = " ".join(part for part in (source, version, heading) if part)
    return f"{prefix}\n{candidate['text']}" if prefix else candidate["text"]
