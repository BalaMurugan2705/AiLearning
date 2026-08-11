from rag.chunking import chunk_document, chunk_text


def test_markdown_reference_doc_makes_one_chunk_per_method():
    text = """# API Reference

## createUser(params)

Creates a new user.

## deleteUser(id)

Deletes a user by id.
"""
    chunks = chunk_document(text, ".md")

    assert len(chunks) == 2
    assert chunks[0].heading_path == ["API Reference", "createUser(params)"]
    assert "Creates a new user." in chunks[0].text
    assert chunks[1].heading_path == ["API Reference", "deleteUser(id)"]
    assert "Deletes a user by id." in chunks[1].text


def test_code_fence_is_never_split_and_stays_with_its_explanation():
    text = """# Getting Started

To initialize the client, install the SDK and create a client instance.

```js
const client = new SDK({ apiKey: "..." });
client.doThing();
```

Once initialized, you can call any method on the client.
"""
    chunks = chunk_document(text, ".md")

    assert len(chunks) == 1
    body = chunks[0].text
    assert '```js\nconst client = new SDK({ apiKey: "..." });\nclient.doThing();\n```' in body
    assert body.index("install the SDK") < body.index("```js") < body.index("Once initialized")


def test_oversized_code_fence_stays_whole_even_past_chunk_size():
    code_lines = "\n".join(f"line{i} = call_something({i})" for i in range(50))
    text = f"""# Example

Here is a long example.

```python
{code_lines}
```

Done.
"""
    chunks = chunk_document(text, ".md", chunk_size=200, chunk_overlap=20)

    fence_chunks = [c for c in chunks if "```python" in c.text]
    assert len(fence_chunks) == 1
    assert code_lines in fence_chunks[0].text


def test_oversized_prose_section_splits_with_overlap():
    paragraphs = [f"This is paragraph number {i} of the guide, with some filler text." for i in range(10)]
    text = "# Long Guide\n\n" + "\n\n".join(paragraphs) + "\n"

    chunks = chunk_document(text, ".md", chunk_size=150, chunk_overlap=30)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.heading_path == ["Long Guide"]
    # consecutive chunks share overlapping trailing/leading text
    assert chunks[0].text[-20:].strip() in chunks[1].text


def test_txt_and_pdf_suffixes_fall_back_to_plain_chunk_text():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."

    for suffix in (".txt", ".pdf"):
        chunks = chunk_document(text, suffix, chunk_size=1000, chunk_overlap=200)
        plain = chunk_text(text, chunk_size=1000, chunk_overlap=200)

        assert [c.text for c in chunks] == plain
        assert all(c.heading_path == [] for c in chunks)


def test_markdown_with_no_headers_behaves_like_plain_chunker():
    text = "Just a paragraph.\n\nAnother paragraph, no headers here at all."

    chunks = chunk_document(text, ".md", chunk_size=1000, chunk_overlap=200)

    assert len(chunks) == 1
    assert chunks[0].heading_path == []
    assert "Just a paragraph." in chunks[0].text
    assert "Another paragraph" in chunks[0].text


def test_skipped_header_level_still_tracks_heading_path():
    text = """# Top

### Deeply Nested

Some content here.
"""
    chunks = chunk_document(text, ".md")

    assert len(chunks) == 1
    assert chunks[0].heading_path == ["Top", "Deeply Nested"]


def test_unclosed_code_fence_does_not_crash_and_degrades_to_prose():
    text = """# Notes

This fence never closes.

```python
print("oops")
"""
    chunks = chunk_document(text, ".md")

    assert len(chunks) == 1
    assert 'print("oops")' in chunks[0].text


def test_bold_label_paragraph_becomes_its_own_chunk_with_extended_heading_path():
    text = """## SDK Version: 1.0.0

**Minimum Requirements:**
- iOS 13.0 or later
- Xcode 13.0 or later
- Swift 5.5 or later

**Dependencies:**
- RainApiSDK
- web3swift

**Supported Card Networks:**
- VISA
- Mastercard
"""
    chunks = chunk_document(text, ".md")

    assert len(chunks) == 3
    by_label = {c.heading_path[-1]: c.text for c in chunks}
    assert set(by_label) == {"Minimum Requirements", "Dependencies", "Supported Card Networks"}
    assert chunks[0].heading_path == ["SDK Version: 1.0.0", "Minimum Requirements"]

    requirements_text = by_label["Minimum Requirements"]
    assert "Swift 5.5" in requirements_text
    assert "VISA" not in requirements_text
    assert "RainApiSDK" not in requirements_text


def test_ordinary_paragraphs_without_bold_labels_still_merge_together():
    text = """# Notes

First paragraph.

Second paragraph.
"""
    chunks = chunk_document(text, ".md")

    assert len(chunks) == 1
    assert "First paragraph." in chunks[0].text
    assert "Second paragraph." in chunks[0].text


def test_inline_bold_text_is_not_mistaken_for_a_label():
    text = """# Overview

The **Omnumi SDK** is a comprehensive iOS framework for card issuance.
"""
    chunks = chunk_document(text, ".md")

    assert len(chunks) == 1
    assert chunks[0].heading_path == ["Overview"]
    assert "The **Omnumi SDK** is a comprehensive iOS framework for card issuance." in chunks[0].text
