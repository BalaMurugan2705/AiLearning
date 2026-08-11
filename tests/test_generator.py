from rag.generator import build_context


def test_build_context_includes_heading_path_in_citation_when_present():
    chunks = [
        {
            "text": "Creates a new user.",
            "metadata": {"source": "api.md", "heading_path": "API Reference > createUser(params)"},
        }
    ]

    context = build_context(chunks)

    assert "[source: api.md → API Reference > createUser(params)]" in context


def test_build_context_falls_back_to_plain_source_when_no_heading_path():
    chunks = [{"text": "Some notes.", "metadata": {"source": "notes.txt", "heading_path": ""}}]

    context = build_context(chunks)

    assert "[source: notes.txt]" in context
    assert "→" not in context
