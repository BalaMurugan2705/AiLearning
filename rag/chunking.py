import re

from rag.config import CHUNK_OVERLAP, CHUNK_SIZE


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph/sentence boundaries.

    Paragraphs are packed greedily into chunks up to chunk_size characters.
    A paragraph longer than chunk_size is split on sentence boundaries, and
    a sentence longer than chunk_size is hard-split.
    Each chunk after the first carries chunk_overlap characters of trailing
    context from the previous chunk, so retrieval doesn't lose context at
    chunk boundaries.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    units: list[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            units.append(para)
        else:
            units.extend(_split_long_unit(para, chunk_size))

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = _overlap_tail(current, chunk_overlap) + "\n\n" + unit
            if len(current) > chunk_size:
                current = unit
        else:
            current = unit

    if current:
        chunks.append(current)

    return chunks


def _split_long_unit(text: str, chunk_size: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > chunk_size:
            if current:
                parts.append(current)
                current = ""
            for i in range(0, len(sentence), chunk_size):
                parts.append(sentence[i : i + chunk_size])
            continue

        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            parts.append(current)
            current = sentence

    if current:
        parts.append(current)

    return parts


def _overlap_tail(text: str, overlap: int) -> str:
    if overlap <= 0 or len(text) <= overlap:
        return text
    return text[-overlap:]
