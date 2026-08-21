"""Tests for the two chunking strategies and parameter-table handling.

Requirement 3 of the Week 3 task demands a structure-aware chunker that
"never splits a parameter row from its header row or a code fence across
chunks". These tests pin that behaviour and the strategy switch that makes
the baseline chunker reachable for markdown.
"""
from rag.chunking import chunk_document

HEADER = "| Parameter | Type | Default | Required | Description |"
DELIM = "|---|---|---|---|---|"


def _table(n_rows: int) -> str:
    rows = [
        f"| param_{i} | int | {i * 100} | no | Description of parameter {i}, "
        f"long enough that the whole table comfortably exceeds a small chunk size. |"
        for i in range(n_rows)
    ]
    return "\n".join([HEADER, DELIM, *rows])


def _row_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith("|")]


def test_baseline_strategy_on_markdown_produces_no_heading_path():
    text = "# Client\n\n## Parameters\n\nSome prose about the client.\n"
    chunks = chunk_document(text, ".md", strategy="baseline")
    assert chunks
    assert all(c.heading_path == [] for c in chunks)


def test_structural_strategy_on_markdown_records_heading_path():
    text = "# Client\n\n## Parameters\n\nSome prose about the client.\n"
    chunks = chunk_document(text, ".md", strategy="structural")
    assert any(c.heading_path == ["Client", "Parameters"] for c in chunks)


def test_small_table_is_never_split():
    text = "# Client\n\n## Parameters\n\n" + _table(3) + "\n"
    chunks = chunk_document(text, ".md", strategy="structural", chunk_size=2000, chunk_overlap=0)
    with_rows = [c for c in chunks if _row_lines(c.text)]
    assert len(with_rows) == 1
    assert len(_row_lines(with_rows[0].text)) == 5  # header + delim + 3 rows


def test_oversized_table_splits_across_chunks():
    text = "# Client\n\n## Parameters\n\n" + _table(20) + "\n"
    chunks = chunk_document(text, ".md", strategy="structural", chunk_size=600, chunk_overlap=0)
    with_rows = [c for c in chunks if _row_lines(c.text)]
    assert len(with_rows) > 1, "a table far larger than chunk_size should split"


def test_every_table_chunk_repeats_the_header_row():
    text = "# Client\n\n## Parameters\n\n" + _table(20) + "\n"
    chunks = chunk_document(text, ".md", strategy="structural", chunk_size=600, chunk_overlap=0)
    for chunk in chunks:
        rows = _row_lines(chunk.text)
        if not rows:
            continue
        assert HEADER in rows, f"chunk lost its header row:\n{chunk.text}"
        assert DELIM in rows, f"chunk lost its delimiter row:\n{chunk.text}"


def test_no_table_row_is_cut_in_half():
    text = "# Client\n\n## Parameters\n\n" + _table(20) + "\n"
    chunks = chunk_document(text, ".md", strategy="structural", chunk_size=600, chunk_overlap=0)
    for chunk in chunks:
        for row in _row_lines(chunk.text):
            assert row.endswith("|"), f"row was cut mid-row: {row!r}"


def test_every_data_row_survives_somewhere():
    text = "# Client\n\n## Parameters\n\n" + _table(20) + "\n"
    chunks = chunk_document(text, ".md", strategy="structural", chunk_size=600, chunk_overlap=0)
    seen = {row for c in chunks for row in _row_lines(c.text)}
    for i in range(20):
        assert any(f"| param_{i} |" in row for row in seen), f"param_{i} row was dropped"


def test_baseline_strategy_does_not_protect_table_rows():
    """The contrast the measurement rests on: the naive chunker cuts rows.

    If this ever starts passing rows intact, the two strategies have stopped
    differing and the comparison is meaningless.
    """
    text = "# Client\n\n## Parameters\n\n" + _table(20) + "\n"
    chunks = chunk_document(text, ".md", strategy="baseline", chunk_size=600, chunk_overlap=0)
    all_rows = [row for c in chunks for row in _row_lines(c.text)]
    assert any(not row.endswith("|") for row in all_rows), (
        "baseline chunker unexpectedly preserved every row boundary"
    )


def test_code_fence_still_atomic_under_structural():
    fence = "```python\n" + "\n".join(f"line_{i} = {i}" for i in range(40)) + "\n```"
    text = "# Client\n\n## Example\n\n" + fence + "\n"
    chunks = chunk_document(text, ".md", strategy="structural", chunk_size=300, chunk_overlap=0)
    holding = [c for c in chunks if "```" in c.text]
    assert len(holding) == 1
    assert holding[0].text.count("```") == 2
