import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

CHROMA_DIR = str(BASE_DIR / os.environ.get("CHROMA_DIR", "chroma_db"))
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "documents")

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "200"))
TOP_K = int(os.environ.get("TOP_K", "4"))

DOCUMENTS_DIR = str(BASE_DIR / "data" / "documents")

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}
