from collections.abc import Iterator

from groq import Groq

from rag.config import GROQ_API_KEY, GROQ_MODEL

SYSTEM_PROMPT = """You are a helpful assistant answering questions using only the \
provided context excerpts from the user's documents.

Rules:
- Answer using only information found in the context below. Do not use outside knowledge.
- If the context does not contain enough information to answer, say so plainly \
instead of guessing.
- When you use a fact from the context, cite it inline with its source tag, e.g. [source: notes.md].
- Be concise and direct."""

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
        source = chunk["metadata"].get("source", "unknown")
        heading_path = chunk["metadata"].get("heading_path", "")
        tag = f"{source} → {heading_path}" if heading_path else source
        parts.append(f"[source: {tag}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def sources_from_chunks(chunks: list[dict]) -> list[str]:
    seen: list[str] = []
    for chunk in chunks:
        source = chunk["metadata"].get("source", "unknown")
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


def answer_question(question: str, chunks: list[dict], max_tokens: int = 2048) -> str:
    """Non-streaming answer, used by the CLI."""
    client = _get_client()
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=max_tokens,
        messages=_build_messages(question, chunks),
    )
    return completion.choices[0].message.content or ""


def stream_answer_text(question: str, chunks: list[dict], max_tokens: int = 2048) -> Iterator[str]:
    """Yield text deltas synchronously, used for CLI live printing."""
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
