import re
from pathlib import Path

from rag.chunking import BASELINE, STRUCTURAL, chunk_document
from rag.config import (
    COLLECTION_BASELINE,
    COLLECTION_STRUCTURAL,
    DOCUMENTS_DIR,
    RERANK_POOL_SIZE,
    TOP_K,
)
from rag.frontmatter import FrontMatterError, parse_front_matter
from rag.generator import answer_question, sources_from_chunks
from rag.loaders import iter_documents
from rag.reranker import CrossEncoderReranker
from rag.store import VectorStore

UNKNOWN = "unknown"

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9 \-]")


class RAGPipeline:
    def __init__(
        self,
        store: VectorStore | None = None,
        strategy: str = STRUCTURAL,
        require_front_matter: bool = False,
    ):
        self.store = (
            store if store is not None else VectorStore(collection_name=collection_for(strategy))
        )
        self.strategy = strategy
        self.require_front_matter = require_front_matter
        self._reranker: CrossEncoderReranker | None = None

    def ingest_path(self, path: str) -> dict:
        """Ingest a single file or a directory of files. Returns a summary dict.

        Every chunk is tagged with source_file, page_id, sdk_version and
        page_type. source_file is derived from the path and is therefore always
        present; the other three come from front matter, which is mandatory
        when require_front_matter is set.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"No such file or directory: {path}")

        files_ingested = 0
        chunks_ingested = 0
        source_files: list[str] = []

        for file_path, raw_text in iter_documents(p):
            source = str(file_path.resolve())
            source_file = _source_file(file_path)
            meta, text = self._read_front_matter(raw_text, file_path)

            chunks = chunk_document(text, file_path.suffix.lower(), strategy=self.strategy)

            # Re-ingesting a source should reflect only its current content,
            # so drop whatever chunks it previously contributed first.
            self.store.delete_by_source(source)
            if not chunks:
                continue

            sdk_version = meta.get("sdk_version", UNKNOWN)
            page_id = meta.get("page_id") or file_path.stem

            texts, metadatas, ids = [], [], []
            for i, chunk in enumerate(chunks):
                heading_path = " > ".join(chunk.heading_path)
                texts.append(chunk.text)
                metadatas.append(
                    {
                        "source_file": source_file,
                        "page_id": page_id,
                        "sdk_version": sdk_version,
                        "page_type": meta.get("page_type", UNKNOWN),
                        "strategy": self.strategy,
                        "heading_path": heading_path,
                        "anchor": _anchor(chunk.heading_path),
                        "chunk_index": i,
                        "source": file_path.name,
                        "path": source,
                    }
                )
                ids.append(f"{sdk_version}:{page_id}:{self.strategy}:{i}")

            self.store.add_texts(texts, metadatas, ids)
            files_ingested += 1
            chunks_ingested += len(chunks)
            source_files.append(source_file)

        return {
            "files_ingested": files_ingested,
            "chunks_ingested": chunks_ingested,
            "source_files": source_files,
        }

    def _read_front_matter(self, raw_text: str, file_path: Path) -> tuple[dict, str]:
        """Return (metadata, body).

        A block that is present but malformed always raises, in both modes —
        silently accepting a half-parsed sdk_version would corrupt the version
        filter invisibly. Only a wholly absent block is tolerated, and only
        when require_front_matter is off.
        """
        if raw_text.lstrip().startswith("---"):
            return parse_front_matter(raw_text)
        if self.require_front_matter:
            raise FrontMatterError(f"{file_path} has no front matter block")
        return {}, raw_text

    def retrieve(
        self, question: str, k: int = TOP_K, where: dict | None = None, rerank: bool = False
    ) -> list[dict]:
        if not rerank:
            return self.store.query(question, k, where=where)

        # Rerank only ever sees a shortlist the cheap hybrid retriever already
        # narrowed down to RERANK_POOL_SIZE candidates — never the whole
        # corpus, since a cross-encoder call costs one model pass per
        # candidate.
        pool = self.store.query(question, RERANK_POOL_SIZE, where=where)
        return self._get_reranker().rerank(question, pool, top_k=k)

    def _get_reranker(self) -> CrossEncoderReranker:
        if self._reranker is None:
            self._reranker = CrossEncoderReranker()
        return self._reranker

    def ask(self, question: str, k: int = TOP_K, where: dict | None = None) -> dict:
        chunks = self.retrieve(question, k, where=where)
        answer = answer_question(question, chunks)
        return {"answer": answer, "sources": sources_from_chunks(chunks)}

    def reset(self) -> None:
        self.store.reset()

    def document_count(self) -> int:
        return self.store.count()


def collection_for(strategy: str) -> str:
    """Each strategy owns a collection so their BM25 corpus statistics stay
    independent — sharing one would double every source sentence's document
    frequency and corrupt both strategies' scores at once."""
    return COLLECTION_BASELINE if strategy == BASELINE else COLLECTION_STRUCTURAL


def _source_file(file_path: Path) -> str:
    """Path relative to the documents root, so v2/client.md and v3/client.md
    stay distinguishable. Files outside that root fall back to their name."""
    resolved = file_path.resolve()
    try:
        return resolved.relative_to(Path(DOCUMENTS_DIR).resolve()).as_posix()
    except ValueError:
        return resolved.name


def _anchor(heading_path: list[str]) -> str:
    """GitHub-style anchor for the deepest heading, so a citation resolves to a
    position on the page rather than just the page."""
    if not heading_path:
        return ""
    slug = _SLUG_STRIP_RE.sub("", heading_path[-1].lower()).strip()
    return "#" + re.sub(r"[\s\-]+", "-", slug) if slug else ""
