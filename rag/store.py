import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from rag.config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL


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

    def add_texts(self, texts: list[str], metadatas: list[dict], ids: list[str]) -> None:
        if not texts:
            return
        # Chroma's add() upserts on duplicate IDs, so re-ingesting a file is safe.
        self._collection.upsert(documents=texts, metadatas=metadatas, ids=ids)

    def query(self, query_text: str, k: int) -> list[dict]:
        if self.count() == 0:
            return []
        k = min(k, self.count())
        result = self._collection.query(query_texts=[query_text], n_results=k)

        hits = []
        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]
        for text, metadata, distance in zip(documents[0], metadatas[0], distances[0]):
            hits.append({"text": text, "metadata": metadata, "distance": distance})
        return hits

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._embedding_fn,
        )
