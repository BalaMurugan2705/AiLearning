"""Metadata, chunk_id and anchor behaviour required by Week 3 requirement 1.

Every chunk must carry source_file, page_id, sdk_version and page_type.
Front matter is enforced strictly for the SDK corpus (require_front_matter=True)
but stays optional for ad-hoc uploads through the web UI, which have none.
"""
import pytest

from rag.frontmatter import FrontMatterError
from rag.pipeline import RAGPipeline

DOC = """---
page_id: client
sdk_version: v3
page_type: reference
---

# Client

## Client.send()

Dispatches a message.
"""


class FakeStore:
    def __init__(self):
        self.added = []
        self.docs = {}

    def add_texts(self, texts, metadatas, ids):
        self.added.append((texts, metadatas, ids))
        for text, metadata, chunk_id in zip(texts, metadatas, ids):
            self.docs[chunk_id] = (text, metadata)

    def delete_by_source(self, path):
        self.docs = {i: tm for i, tm in self.docs.items() if tm[1]["path"] != path}

    def count(self):
        return len(self.docs)


def _ingest(tmp_path, text, name="client.md", **kwargs):
    doc = tmp_path / name
    doc.write_text(text, encoding="utf-8")
    store = FakeStore()
    RAGPipeline(store=store, **kwargs).ingest_path(str(doc))
    return store


def test_every_chunk_carries_the_four_required_fields(tmp_path):
    store = _ingest(tmp_path, DOC)
    _, metadatas, _ = store.added[0]
    for meta in metadatas:
        for field in ("source_file", "page_id", "sdk_version", "page_type"):
            assert meta.get(field), f"{field} missing or empty: {meta}"


def test_front_matter_values_reach_the_metadata(tmp_path):
    store = _ingest(tmp_path, DOC)
    _, metadatas, _ = store.added[0]
    assert metadatas[0]["page_id"] == "client"
    assert metadatas[0]["sdk_version"] == "v3"
    assert metadatas[0]["page_type"] == "reference"


def test_front_matter_is_stripped_from_chunk_text(tmp_path):
    store = _ingest(tmp_path, DOC)
    texts, _, _ = store.added[0]
    assert not any("page_id:" in t for t in texts)


def test_chunk_id_is_human_resolvable(tmp_path):
    store = _ingest(tmp_path, DOC)
    _, _, ids = store.added[0]
    assert ids[0] == "v3:client:structural:0"


def test_chunk_id_encodes_strategy_so_collections_cannot_collide(tmp_path):
    store = _ingest(tmp_path, DOC, strategy="baseline")
    _, _, ids = store.added[0]
    assert ids[0].startswith("v3:client:baseline:")


def test_strategy_is_recorded_in_metadata(tmp_path):
    store = _ingest(tmp_path, DOC, strategy="baseline")
    _, metadatas, _ = store.added[0]
    assert metadatas[0]["strategy"] == "baseline"


def test_anchor_is_github_style_slug_of_deepest_heading(tmp_path):
    store = _ingest(tmp_path, DOC)
    _, metadatas, _ = store.added[0]
    anchors = {m["anchor"] for m in metadatas}
    assert "#clientsend" in anchors


def test_baseline_chunks_have_no_anchor(tmp_path):
    store = _ingest(tmp_path, DOC, strategy="baseline")
    _, metadatas, _ = store.added[0]
    assert all(m["anchor"] == "" for m in metadatas)


def test_strict_mode_rejects_a_page_with_no_front_matter(tmp_path):
    doc = tmp_path / "client.md"
    doc.write_text("# Client\n\nNo front matter here.\n", encoding="utf-8")
    pipeline = RAGPipeline(store=FakeStore(), require_front_matter=True)
    with pytest.raises(FrontMatterError):
        pipeline.ingest_path(str(doc))


def test_lenient_mode_still_sets_source_file_without_front_matter(tmp_path):
    """A chunk with no source_file is a failed ingest, so source_file is
    derived from the path and can never be absent."""
    store = _ingest(tmp_path, "# Notes\n\nSome text.\n", name="notes.md")
    _, metadatas, _ = store.added[0]
    assert metadatas[0]["source_file"] == "notes.md"
    assert metadatas[0]["sdk_version"] == "unknown"


def test_source_file_is_relative_to_the_documents_dir():
    """v2/client.md and v3/client.md share a filename, so source_file must
    carry enough path to tell them apart."""
    store = FakeStore()
    RAGPipeline(store=store, require_front_matter=True).ingest_path(
        "data/documents/v3/client.md"
    )
    _, metadatas, _ = store.added[0]
    assert metadatas[0]["source_file"] == "v3/client.md"
    assert metadatas[0]["sdk_version"] == "v3"


def test_strategy_selects_the_matching_collection():
    """Each strategy owns a collection, so their BM25 corpus statistics stay
    independent and neither can retrieve the other's chunks."""
    from rag.config import COLLECTION_BASELINE, COLLECTION_STRUCTURAL
    from rag.pipeline import collection_for

    assert collection_for("structural") == COLLECTION_STRUCTURAL
    assert collection_for("baseline") == COLLECTION_BASELINE


def test_ingest_reports_which_pages_it_touched():
    store = FakeStore()
    result = RAGPipeline(store=store, require_front_matter=True).ingest_path(
        "data/documents/v3"
    )
    assert result["files_ingested"] == 6
    assert sorted(result["source_files"]) == [
        "v3/auth.md",
        "v3/client.md",
        "v3/errors.md",
        "v3/pagination.md",
        "v3/streaming.md",
        "v3/webhooks.md",
    ]
