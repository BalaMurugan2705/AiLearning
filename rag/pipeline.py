import hashlib
from pathlib import Path

from rag.chunking import chunk_text
from rag.config import TOP_K
from rag.generator import (
    answer_question,
    async_stream_answer_text,
    sources_from_chunks,
    stream_answer_text,
)
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
            chunks = chunk_text(text)
            if not chunks:
                continue

            source = str(file_path)
            texts, metadatas, ids = [], [], []
            for i, chunk in enumerate(chunks):
                chunk_id = hashlib.sha256(f"{source}:{i}".encode()).hexdigest()
                texts.append(chunk)
                metadatas.append({"source": file_path.name, "path": source, "chunk_index": i})
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

    def ask_stream(self, question: str, k: int = TOP_K):
        """Sync generator: retrieves chunks, then yields answer text deltas.
        The CLI calls retrieve() separately beforehand so it can print sources
        after streaming completes."""
        chunks = self.retrieve(question, k)
        yield from stream_answer_text(question, chunks)

    async def ask_stream_async(self, question: str, k: int = TOP_K):
        """Async generator for the web UI: retrieves, then yields
        {"type": "token", "text": ...} events followed by a final
        {"type": "sources", "sources": [...]} event."""
        chunks = self.retrieve(question, k)
        async for text in async_stream_answer_text(question, chunks):
            yield {"type": "token", "text": text}
        yield {"type": "sources", "sources": sources_from_chunks(chunks)}

    def reset(self) -> None:
        self.store.reset()

    def document_count(self) -> int:
        return self.store.count()
