from pathlib import Path

from rag.pipeline import RAGPipeline
from rag.store import VectorStore

WEEK7_DOCS_DIR = (
    Path(__file__).resolve().parent.parent
    / "data" / "documents" / "input_files" / "developer_documentations"
)


def get_pipeline(persist_dir: str | None = None, collection_name: str = "week7_docs") -> RAGPipeline:
    """Build (and lazily ingest) the RAG pipeline over the 3 developer-doc PDFs.

    persist_dir=None uses the app's default Chroma directory so a normal
    agent run reuses the index across processes; tests pass an isolated
    tmp_path so they never touch or depend on that persisted index.
    """
    store_kwargs = {"collection_name": collection_name}
    if persist_dir is not None:
        store_kwargs["persist_dir"] = persist_dir
    store = VectorStore(**store_kwargs)
    pipeline = RAGPipeline(store=store, require_front_matter=False)
    if pipeline.document_count() == 0:
        pipeline.ingest_path(str(WEEK7_DOCS_DIR))
    return pipeline


def search_docs_raw(pipeline: RAGPipeline, query: str, k: int = 4) -> list[dict]:
    return pipeline.retrieve(query, k=k)
