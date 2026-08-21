import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

CHROMA_DIR = str(BASE_DIR / os.environ.get("CHROMA_DIR", "chroma_db"))
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "documents")

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "200"))
TOP_K = int(os.environ.get("TOP_K", "4"))

# One collection per chunking strategy. Sharing a collection would let the two
# strategies' chunks contaminate each other's BM25 corpus statistics, since the
# same source sentence would appear twice and its document frequency would be
# inflated by an artifact of the experiment rather than by the corpus.
COLLECTION_BASELINE = os.environ.get("COLLECTION_BASELINE", "docs_baseline")
COLLECTION_STRUCTURAL = os.environ.get("COLLECTION_STRUCTURAL", "docs_structural")

# Refusal must be forced, not suggested. The exact string makes a refusal
# machine-detectable; a soft refusal ("the docs don't say, but generally...")
# is a hallucination wearing a disclaimer and no automated check would catch it.
REFUSAL_MESSAGE = "I cannot answer that from the indexed documentation."

# Calibrated by eval/run_eval.py against held-out calibration questions, never
# against the 8 reported questions. Cosine distance, so bounded in [0, 2].
REFUSAL_DISTANCE_THRESHOLD = float(os.environ.get("REFUSAL_DISTANCE_THRESHOLD", "0.85"))

# A cross-encoder reads the query and one candidate chunk together, so it can
# recognize a paraphrase (chunk says "HMAC-SHA256", query says "hashing
# algorithm") that keyword overlap alone would rank low. Too slow to run over
# a whole corpus, so it only ever sees a short list already narrowed down by
# the cheaper hybrid retriever.
RERANK_MODEL = os.environ.get("RERANK_MODEL", "cross-encoder/ms-marco-TinyBERT-L-2-v2")
RERANK_POOL_SIZE = int(os.environ.get("RERANK_POOL_SIZE", "25"))

DOCUMENTS_DIR = str(BASE_DIR / "data" / "documents")

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}
