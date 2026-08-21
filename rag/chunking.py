import re
from dataclasses import dataclass, field

from rag.config import CHUNK_OVERLAP, CHUNK_SIZE

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
# _FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_BOLD_LABEL_LINE_RE = re.compile(r"^\*\*(.+?):?\*\*$")

_FENCE_RE = re.compile(
    r"^(`{3,}|~{3,}).*?$.*?^\1\s*$",
    re.MULTILINE | re.DOTALL
)

# A markdown table: a header row, a delimiter row of dashes/colons, then any
# number of data rows. Matched as one span so the table can be treated as an
# atomic unit rather than as ordinary prose.
_TABLE_RE = re.compile(
    r"^[ \t]*\|.*\|[ \t]*$\n"
    r"^[ \t]*\|[ \t:\-|]+\|[ \t]*$"
    r"(?:\n^[ \t]*\|.*\|[ \t]*$)*",
    re.MULTILINE,
)

BASELINE = "baseline"
STRUCTURAL = "structural"


@dataclass
class Chunk:
    text: str
    heading_path: list[str] = field(default_factory=list)


def chunk_document(
    text: str,
    suffix: str,
    strategy: str = STRUCTURAL,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """Chunk a document under an explicit strategy.

    `suffix` decides what is *possible* (only markdown carries reliable header
    structure); `strategy` decides what is *used*. The baseline strategy is the
    plain fixed-size paragraph/sentence chunker, applied even to markdown, so
    the two strategies can be measured over identical input.
    """
    if strategy == BASELINE or suffix != ".md":
        return [Chunk(text=t) for t in chunk_text(text, chunk_size, chunk_overlap)]
    return _chunk_markdown(text, chunk_size, chunk_overlap)


def _chunk_markdown(text: str, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    fence_spans = [m.span() for m in _FENCE_RE.finditer(text)]

    def in_fence(pos: int) -> bool:
        return any(start <= pos < end for start, end in fence_spans)

    headers = [
        (len(m.group(1)), m.group(2).strip(), m.start(), m.end())
        for m in _HEADER_RE.finditer(text)
        if not in_fence(m.start())
    ]

    sections: list[tuple[list[str], str]] = []

    first_start = headers[0][2] if headers else len(text)
    preamble = text[:first_start]
    if preamble.strip():
        sections.append(([], preamble))

    stack: list[tuple[int, str]] = []
    for i, (level, title, _start, end) in enumerate(headers):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        heading_path = [t for _, t in stack]

        body_start = end + 1 if end < len(text) and text[end] == "\n" else end
        body_end = headers[i + 1][2] if i + 1 < len(headers) else len(text)
        sections.append((heading_path, text[body_start:body_end]))

    chunks: list[Chunk] = []
    for heading_path, body in sections:
        for label, subbody in _split_by_bold_labels(body):
            sub_heading_path = heading_path + [label] if label else heading_path
            prefix = " > ".join(sub_heading_path)
            for chunk_body in _pack_section(subbody, chunk_size, chunk_overlap):
                full_text = f"{prefix}\n\n{chunk_body}" if prefix else chunk_body
                chunks.append(Chunk(text=full_text, heading_path=sub_heading_path))

    return chunks


def _split_by_bold_labels(body: str) -> list[tuple[str | None, str]]:
    """Split a section body on paragraphs whose first line is a bare bold
    label (e.g. "**Minimum Requirements:**" followed by its list on the same
    paragraph). Each labeled paragraph becomes its own segment, isolated from
    sibling paragraphs; runs of unlabeled paragraphs stay merged together,
    same as before this split existed."""
    paras: list[tuple[int, int]] = []
    pos = 0
    for m in re.finditer(r"\n\s*\n", body):
        paras.append((pos, m.start()))
        pos = m.end()
    paras.append((pos, len(body)))

    tagged: list[tuple[str | None, str]] = []
    for start, end in paras:
        raw = body[start:end]
        if not raw.strip():
            continue
        stripped = raw.strip()
        first_line, _, rest = stripped.partition("\n")
        m = _BOLD_LABEL_LINE_RE.match(first_line.strip())
        tagged.append((m.group(1).strip(), rest) if m else (None, raw))

    if not any(label for label, _ in tagged):
        return [(None, body)]

    segments: list[tuple[str | None, str]] = []
    run: list[str] = []
    for label, text in tagged:
        if label is None:
            run.append(text)
            continue
        if run:
            segments.append((None, "\n\n".join(run)))
            run = []
        segments.append((label, text))
    if run:
        segments.append((None, "\n\n".join(run)))

    return segments


def _pack_section(body: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Greedily pack a section's units into chunks. Code-fence and table units
    are never split mid-unit, even when one exceeds chunk_size; an oversized
    table is divided on row boundaries instead, carrying its header row into
    every part."""
    units: list[tuple[str, str]] = []
    for unit_text, kind in _units_from_text(body, chunk_size):
        if kind == "table" and len(unit_text) > chunk_size:
            units.extend((part, "table") for part in _split_table_by_rows(unit_text, chunk_size))
        else:
            units.append((unit_text, kind))

    if not units:
        return []

    chunks: list[str] = []
    current = ""
    for unit_text, kind in units:
        atomic = kind != "plain"
        candidate = f"{current}\n\n{unit_text}" if current else unit_text
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
            tail = _overlap_tail(current, chunk_overlap)
            current = f"{tail}\n\n{unit_text}" if tail else unit_text
            if len(current) > chunk_size and not atomic:
                current = unit_text
        else:
            current = unit_text

    if current:
        chunks.append(current)

    return chunks


def _split_table_by_rows(table: str, chunk_size: int) -> list[str]:
    """Split an oversized markdown table on row boundaries, repeating the
    header and delimiter rows into every part.

    The header row carries the column semantics. A fragment reading
    `| retry_backoff_ms | int | 2000 | no |` with no header is retrievable but
    not interpretable — 2000 could be milliseconds, bytes or a rate. Repeating
    ~80 characters of header turns each part into a self-contained fact.
    """
    lines = [ln for ln in table.splitlines() if ln.strip()]
    if len(lines) < 3:
        return [table]

    header, delim, rows = lines[0], lines[1], lines[2:]
    prefix = f"{header}\n{delim}"

    parts: list[str] = []
    current: list[str] = []
    for row in rows:
        candidate = "\n".join([prefix, *current, row])
        if current and len(candidate) > chunk_size:
            parts.append("\n".join([prefix, *current]))
            current = [row]
        else:
            current.append(row)

    if current:
        parts.append("\n".join([prefix, *current]))

    return parts or [table]


def _units_from_text(text: str, chunk_size: int) -> list[tuple[str, str]]:
    """Split section text into (unit_text, kind) pairs, in order, where kind is
    one of "code", "table" or "plain". Code fences and tables become single
    atomic units; a table found inside a fence is left as part of the fence."""
    fence_spans = [(m.start(), m.end(), "code", m.group()) for m in _FENCE_RE.finditer(text)]

    def in_fence(pos: int) -> bool:
        return any(start <= pos < end for start, end, _, _ in fence_spans)

    table_spans = [
        (m.start(), m.end(), "table", m.group())
        for m in _TABLE_RE.finditer(text)
        if not in_fence(m.start())
    ]

    units: list[tuple[str, str]] = []
    pos = 0
    for start, end, kind, raw in sorted(fence_spans + table_spans):
        if start > pos:
            units.extend(_plain_units(text[pos:start], chunk_size))
        units.append((raw, kind))
        pos = end
    if pos < len(text):
        units.extend(_plain_units(text[pos:], chunk_size))
    return units


def _plain_units(text: str, chunk_size: int) -> list[tuple[str, str]]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: list[tuple[str, str]] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            units.append((para, "plain"))
        else:
            units.extend((u, "plain") for u in _split_long_unit(para, chunk_size))
    return units


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
