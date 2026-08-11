import hashlib
from pathlib import Path

from rag.chunking import chunk_document
from rag.config import TOP_K
from rag.generator import answer_question, sources_from_chunks
from rag.loaders import iter_documents
from rag.store import VectorStore


class RAGPipeline:
    def __init__(self, store: VectorStore | None = None):
        self.store = store or VectorStore()

    def ingest_path(self, path: str) -> dict:
        """Ingest a single file or a directory of files. Returns a summary dict."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"No such file or directory: {path}")

        files_ingested = 0
        chunks_ingested = 0

        for file_path, text in iter_documents(p):
            # Canonicalize so the same file is recognized as one source
            # regardless of whether it's referenced via a relative or
            # absolute path across different ingest calls.
            source = str(file_path.resolve())
            chunks = chunk_document(text, file_path.suffix.lower())

            # Re-ingesting a source should reflect only its current content,
            # so drop whatever chunks it previously contributed first.
            self.store.delete_by_source(source)
            if not chunks:
                continue

            texts, metadatas, ids = [], [], []
            for i, chunk in enumerate(chunks):
                chunk_id = hashlib.sha256(f"{source}:{i}".encode()).hexdigest()
                texts.append(chunk.text)
                metadatas.append(
                    {
                        "source": file_path.name,
                        "path": source,
                        "chunk_index": i,
                        "heading_path": " > ".join(chunk.heading_path),
                    }
                )
                ids.append(chunk_id)

            self.store.add_texts(texts, metadatas, ids)
            files_ingested += 1
            chunks_ingested += len(chunks)

        return {"files_ingested": files_ingested, "chunks_ingested": chunks_ingested}

    def retrieve(self, question: str, k: int = TOP_K) -> list[dict]:
        return self.store.query(question, k)

    def ask(self, question: str, k: int = TOP_K) -> dict:
        chunks = self.retrieve(question, k)
        answer = answer_question(question, chunks)
        return {"answer": answer, "sources": sources_from_chunks(chunks)}

    def reset(self) -> None:
        self.store.reset()

    def document_count(self) -> int:
        return self.store.count()
