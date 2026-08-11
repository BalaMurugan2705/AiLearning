import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from rank_bm25 import BM25Okapi

from rag.config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL
from rag.retrieval import reciprocal_rank_fusion, tokenize


class VectorStore:
    def __init__(
        self,
        persist_dir: str = CHROMA_DIR,
        collection_name: str = COLLECTION_NAME,
        embedding_model: str = EMBEDDING_MODEL,
    ):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._embedding_fn = SentenceTransformerEmbeddingFunction(model_name=embedding_model)
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedding_fn,
        )
        self._bm25: BM25Okapi | None = None
        self._bm25_lookup: dict[str, dict] = {}

    def add_texts(self, texts: list[str], metadatas: list[dict], ids: list[str]) -> None:
        if not texts:
            return
        # Chroma's add() upserts on duplicate IDs, so re-ingesting a file is safe.
        self._collection.upsert(documents=texts, metadatas=metadatas, ids=ids)
        self._bm25 = None
        self._bm25_lookup = {}

    def query(self, query_text: str, k: int) -> list[dict]:
        """Hybrid retrieval: fuse dense (embedding) search with BM25 keyword
        search via Reciprocal Rank Fusion, so exact technical terms (version
        numbers, method names) surface even when they lose on pure semantic
        similarity to a broader, more generic-sounding chunk."""
        total = self.count()
        if total == 0:
            return []
        k = min(k, total)
        pool = min(max(k * 4, 20), total)

        dense = self._collection.query(query_texts=[query_text], n_results=pool)
        dense_ids = (dense.get("ids") or [[]])[0]
        lookup = {
            chunk_id: {"text": text, "metadata": metadata}
            for chunk_id, text, metadata in zip(
                dense_ids, (dense.get("documents") or [[]])[0], (dense.get("metadatas") or [[]])[0]
            )
        }

        keyword_ids = self._bm25_search(query_text, pool)
        lookup.update({i: self._bm25_lookup[i] for i in keyword_ids})

        fused_ids = reciprocal_rank_fusion([dense_ids, keyword_ids])[:k]
        return [
            {"text": lookup[chunk_id]["text"], "metadata": lookup[chunk_id]["metadata"], "distance": rank}
            for rank, chunk_id in enumerate(fused_ids)
        ]

    def _bm25_search(self, query_text: str, pool: int) -> list[str]:
        self._ensure_bm25()
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query_text))
        ids = list(self._bm25_lookup)
        ranked = sorted(range(len(ids)), key=lambda i: scores[i], reverse=True)
        return [ids[i] for i in ranked[:pool]]

    def _ensure_bm25(self) -> None:
        if self._bm25_lookup:
            return
        data = self._collection.get(include=["documents", "metadatas"])
        ids = data.get("ids") or []
        documents = data.get("documents") or []
        metadatas = data.get("metadatas") or []
        self._bm25_lookup = {
            chunk_id: {"text": text, "metadata": metadata}
            for chunk_id, text, metadata in zip(ids, documents, metadatas)
        }
        if ids:
            self._bm25 = BM25Okapi([tokenize(text) for text in documents])

    def delete_by_source(self, path: str) -> None:
        self._collection.delete(where={"path": path})
        self._bm25 = None
        self._bm25_lookup = {}

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._embedding_fn,
        )
        self._bm25 = None
        self._bm25_lookup = {}
