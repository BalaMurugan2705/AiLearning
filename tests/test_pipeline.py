from rag.pipeline import RAGPipeline


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


def test_ingest_path_tags_markdown_chunks_with_heading_path(tmp_path):
    doc = tmp_path / "api.md"
    doc.write_text("# API Reference\n\n## createUser(params)\n\nCreates a new user.\n")

    store = FakeStore()
    RAGPipeline(store=store).ingest_path(str(doc))

    _, metadatas, _ = store.added[0]
    assert metadatas[0]["heading_path"] == "API Reference > createUser(params)"


def test_ingest_path_leaves_heading_path_empty_for_txt(tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("Just some notes.")

    store = FakeStore()
    RAGPipeline(store=store).ingest_path(str(doc))

    _, metadatas, _ = store.added[0]
    assert metadatas[0]["heading_path"] == ""


def test_reingesting_same_file_removes_stale_chunks_from_shrunk_content(tmp_path):
    doc = tmp_path / "notes.md"
    store = FakeStore()
    pipeline = RAGPipeline(store=store)

    doc.write_text("# One\n\nFirst paragraph.\n\n# Two\n\nSecond paragraph.\n\n# Three\n\nThird paragraph.\n")
    pipeline.ingest_path(str(doc))
    assert store.count() == 3

    doc.write_text("# One\n\nFirst paragraph only now.\n")
    pipeline.ingest_path(str(doc))

    assert store.count() == 1
    remaining_text = next(iter(store.docs.values()))[0]
    assert "First paragraph only now." in remaining_text


def test_ingesting_file_that_now_yields_no_chunks_clears_its_old_chunks(tmp_path):
    doc = tmp_path / "notes.md"
    store = FakeStore()
    pipeline = RAGPipeline(store=store)

    doc.write_text("# One\n\nSome content.\n")
    pipeline.ingest_path(str(doc))
    assert store.count() == 1

    doc.write_text("   \n")
    pipeline.ingest_path(str(doc))

    assert store.count() == 0


def test_ingest_path_treats_relative_and_absolute_paths_as_the_same_source(tmp_path, monkeypatch):
    doc = tmp_path / "notes.md"
    doc.write_text("# One\n\nFirst version.\n")

    store = FakeStore()
    pipeline = RAGPipeline(store=store)
    pipeline.ingest_path(str(doc))  # absolute
    assert store.count() == 1

    doc.write_text("# One\n\nSecond version.\n")
    monkeypatch.chdir(tmp_path)
    pipeline.ingest_path("notes.md")  # relative, same file

    assert store.count() == 1
    remaining_text = next(iter(store.docs.values()))[0]
    assert "Second version." in remaining_text
