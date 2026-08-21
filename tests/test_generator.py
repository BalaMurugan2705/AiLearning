"""Context labelling for chunks that predate the SDK metadata schema.

Ad-hoc uploads through the web UI carry `source` but no `source_file`,
`anchor` or front matter. Those chunks must still be citable rather than
crashing or labelling themselves "unknown".
"""
from rag.generator import build_context, sources_from_chunks


def test_build_context_labels_a_chunk_with_its_id_and_location():
    chunks = [
        {
            "chunk_id": "v3:client:structural:2",
            "text": "Creates a new user.",
            "metadata": {
                "source_file": "v3/client.md",
                "anchor": "#createuserparams",
                "heading_path": "API Reference > createUser(params)",
            },
        }
    ]

    context = build_context(chunks)

    assert "[chunk: v3:client:structural:2 | v3/client.md#createuserparams]" in context
    assert "Creates a new user." in context


def test_build_context_falls_back_to_legacy_source_metadata():
    chunks = [
        {
            "chunk_id": "notes:0",
            "text": "Some notes.",
            "metadata": {"source": "notes.txt", "heading_path": ""},
        }
    ]

    context = build_context(chunks)

    assert "[chunk: notes:0 | notes.txt]" in context


def test_sources_prefers_source_file_and_deduplicates():
    chunks = [
        {"text": "a", "metadata": {"source_file": "v3/client.md"}},
        {"text": "b", "metadata": {"source_file": "v3/client.md"}},
        {"text": "c", "metadata": {"source": "notes.txt"}},
    ]

    assert sources_from_chunks(chunks) == ["v3/client.md", "notes.txt"]
