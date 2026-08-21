import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from rank_bm25 import BM25Okapi

from rag.config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL
from rag.retrieval import fuse_with_scores, tokenize


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
        self._collection = self._create_collection()
        self._bm25: BM25Okapi | None = None
        self._bm25_lookup: dict[str, dict] = {}

    def _create_collection(self):
        # Cosine rather than Chroma's default squared L2. Ranking is the same
        # either way, but the refusal gate thresholds on the raw distance, and
        # cosine is bounded in [0, 2] whereas squared L2 has no stable scale.
        return self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add_texts(self, texts: list[str], metadatas: list[dict], ids: list[str]) -> None:
        if not texts:
            return
        # Chroma's add() upserts on duplicate IDs, so re-ingesting a file is safe.
        self._collection.upsert(documents=texts, metadatas=metadatas, ids=ids)
        self._invalidate_bm25()

    def query(self, query_text: str, k: int, where: dict | None = None) -> list[dict]:
        """Hybrid retrieval: fuse dense (embedding) search with BM25 keyword
        search via Reciprocal Rank Fusion, so exact technical terms (version
        numbers, method names) surface even when they lose on pure semantic
        similarity to a broader, more generic-sounding chunk.

        `where` is a plain equality filter on chunk metadata, applied to BOTH
        legs. Applying it to the dense leg alone would let a filtered-out chunk
        re-enter the results through the keyword leg.
        """
        total = self.count()
        if total == 0:
            return []
        k = min(k, total)
        pool = min(max(k * 4, 20), total)

        dense = self._collection.query(
            query_texts=[query_text], n_results=pool, where=where or None
        )
        dense_ids = (dense.get("ids") or [[]])[0]
        dense_distances = (dense.get("distances") or [[]])[0]
        distance_by_id = {
            chunk_id: float(distance)
            for chunk_id, distance in zip(dense_ids, dense_distances)
        }
        lookup = {
            chunk_id: {"text": text, "metadata": metadata}
            for chunk_id, text, metadata in zip(
                dense_ids, (dense.get("documents") or [[]])[0], (dense.get("metadatas") or [[]])[0]
            )
        }

        keyword_ids, bm25_by_id = self._bm25_search(query_text, pool, where)
        lookup.update({i: self._bm25_lookup[i] for i in keyword_ids})

        fused = fuse_with_scores([dense_ids, keyword_ids])[:k]
        return [
            {
                "chunk_id": chunk_id,
                "text": lookup[chunk_id]["text"],
                "metadata": lookup[chunk_id]["metadata"],
                "dense_distance": distance_by_id.get(chunk_id),
                "bm25_score": bm25_by_id.get(chunk_id),
                "rrf_score": rrf_score,
                "rank": rank,
            }
            for rank, (chunk_id, rrf_score) in enumerate(fused)
        ]

    def _bm25_search(
        self, query_text: str, pool: int, where: dict | None = None
    ) -> tuple[list[str], dict[str, float]]:
        self._ensure_bm25()
        if self._bm25 is None:
            return [], {}

        scores = self._bm25.get_scores(tokenize(query_text))
        ids = list(self._bm25_lookup)
        eligible = [
            i
            for i, chunk_id in enumerate(ids)
            if _matches(self._bm25_lookup[chunk_id]["metadata"], where)
        ]
        ranked = sorted(eligible, key=lambda i: scores[i], reverse=True)[:pool]
        return [ids[i] for i in ranked], {ids[i]: float(scores[i]) for i in ranked}

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

    def _invalidate_bm25(self) -> None:
        self._bm25 = None
        self._bm25_lookup = {}

    def get_by_id(self, chunk_id: str) -> dict | None:
        """Resolve a chunk_id back to its text and metadata, so a citation can
        be verified against the chunk it claims to come from."""
        data = self._collection.get(ids=[chunk_id], include=["documents", "metadatas"])
        if not (data.get("ids") or []):
            return None
        return {
            "chunk_id": chunk_id,
            "text": (data.get("documents") or [""])[0],
            "metadata": (data.get("metadatas") or [{}])[0],
        }

    def all_ids(self) -> set[str]:
        """Every chunk_id currently indexed. Used to prove an incremental
        ingest left the previously indexed pages untouched."""
        return set(self._collection.get(include=[]).get("ids") or [])

    def delete_by_source(self, path: str) -> None:
        self._collection.delete(where={"path": path})
        self._invalidate_bm25()

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._create_collection()
        self._invalidate_bm25()


def _matches(metadata: dict, where: dict | None) -> bool:
    if not where:
        return True
    return all(metadata.get(field) == value for field, value in where.items())
