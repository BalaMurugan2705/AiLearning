import hashlib
import re
from collections.abc import Iterator

from groq import Groq

from rag.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    REFUSAL_DISTANCE_THRESHOLD,
    REFUSAL_MESSAGE,
)

SYSTEM_PROMPT = f"""You answer questions about SDK reference documentation using \
only the context excerpts supplied to you.

Rules:
- Use only the supplied context. Prior knowledge about any SDK, including \
conventions you believe are standard practice, is forbidden as a source.
- Every sentence that states a fact must end with a citation naming the chunk it \
came from, in the form [chunk: <chunk_id>]. Cite only chunk ids that appear in \
the context you were given.
- If the context does not contain the answer, reply with exactly this sentence \
and nothing else:
{REFUSAL_MESSAGE}
- If part of the question is supported by the context and part is not, answer the \
supported part with citations, then state plainly which part is not present in \
the documentation.
- Never infer, estimate, round, or extrapolate a value that is not written in the \
context. A plausible-looking default is still an invention.
- Be concise and direct."""

# Only the current SYSTEM_PROMPT text is ever kept — an older version's exact
# wording isn't archived anywhere, so a trace logging this tag can prove which
# prompt *changed* but can't reconstruct one after SYSTEM_PROMPT moves on.
PROMPT_VERSION = "sysprompt-" + hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:10]

_CITATION_RE = re.compile(r"\[chunk:\s*([^\]\s|]+)")

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def build_context(chunks: list[dict]) -> str:
    if not chunks:
        return "(no relevant context was found in the indexed documents)"

    parts = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        source_file = metadata.get("source_file") or metadata.get("source", "unknown")
        location = f"{source_file}{metadata.get('anchor', '')}"
        chunk_id = chunk.get("chunk_id", "unknown")
        parts.append(f"[chunk: {chunk_id} | {location}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def should_refuse(chunks: list[dict], threshold: float = REFUSAL_DISTANCE_THRESHOLD) -> bool:
    """Refuse before generating when nothing retrieved is close enough.

    Thresholds the raw cosine distance from the dense leg, not the fused RRF
    score: an RRF score is a function of rank alone, so the top hit of a
    nonsense query scores the same as the top hit of a perfect one.

    Chunks that surfaced only through BM25 carry no dense distance and are
    treated as no evidence, which is the conservative direction for a gate
    whose whole purpose is to avoid answering without support.
    """
    distances = [
        chunk["dense_distance"]
        for chunk in chunks
        if chunk.get("dense_distance") is not None
    ]
    if not distances:
        return True
    return min(distances) > threshold


def extract_citations(answer: str) -> list[str]:
    """Pull every cited chunk_id out of an answer, in order, without repeats."""
    seen: list[str] = []
    for match in _CITATION_RE.finditer(answer):
        chunk_id = match.group(1).strip()
        if chunk_id not in seen:
            seen.append(chunk_id)
    return seen


def verify_citations(
    answer: str, chunks: list[dict], expected_span: str | None = None
) -> dict:
    """Check that every citation resolves to a chunk that was actually retrieved,
    and optionally that a cited chunk really contains the claimed fact.

    Resolving is not sufficient on its own: a real chunk_id attached to a claim
    that chunk never makes is the failure mode the grader checks by hand.
    """
    available = {chunk.get("chunk_id"): chunk for chunk in chunks}
    cited = extract_citations(answer)
    unresolvable = [chunk_id for chunk_id in cited if chunk_id not in available]

    report = {
        "cited": cited,
        "unresolvable": unresolvable,
        "ok": bool(cited) and not unresolvable,
    }

    if expected_span is not None:
        report["span_supported"] = any(
            expected_span in available[chunk_id]["text"]
            for chunk_id in cited
            if chunk_id in available
        )

    return report


def sources_from_chunks(chunks: list[dict]) -> list[str]:
    seen: list[str] = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        source = metadata.get("source_file") or metadata.get("source", "unknown")
        if source not in seen:
            seen.append(source)
    return seen


def _build_messages(question: str, chunks: list[dict]) -> list[dict]:
    context = build_context(chunks)
    user_content = f"Context:\n\n{context}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def answer_question(
    question: str,
    chunks: list[dict],
    max_tokens: int = 2048,
    threshold: float = REFUSAL_DISTANCE_THRESHOLD,
) -> str:
    """Non-streaming answer, used by the CLI and the eval harness."""
    if should_refuse(chunks, threshold):
        return REFUSAL_MESSAGE

    client = _get_client()
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=max_tokens,
        messages=_build_messages(question, chunks),
    )
    return completion.choices[0].message.content or ""


def stream_answer_text(
    question: str,
    chunks: list[dict],
    max_tokens: int = 2048,
    threshold: float = REFUSAL_DISTANCE_THRESHOLD,
) -> Iterator[str]:
    """Yield text deltas synchronously, used for CLI live printing."""
    if should_refuse(chunks, threshold):
        yield REFUSAL_MESSAGE
        return

    client = _get_client()
    stream = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=max_tokens,
        messages=_build_messages(question, chunks),
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
