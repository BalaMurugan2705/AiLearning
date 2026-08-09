# RAG App

A minimal Retrieval-Augmented Generation app: ingest your documents (.txt, .md, .pdf),
embed and index them locally with [ChromaDB](https://www.trychroma.com/) +
[sentence-transformers](https://www.sbert.net/), retrieve the most relevant chunks
for a question, and answer with a free Groq-hosted LLM grounded in that context.

Two interfaces are included:
- **CLI** (`cli.py`) — ingest documents and ask questions from the terminal.
- **Web UI** (`app.py`) — a small FastAPI app with a drag-and-drop chat interface.

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
# then edit .env and set GROQ_API_KEY (free key: https://console.groq.com/keys)
```

The first run downloads the local embedding model (`all-MiniLM-L6-v2`, ~80MB) —
no API key is needed for embeddings, only for generation.

## CLI usage

```bash
# Ingest a file or a whole directory
python cli.py ingest data/documents
python cli.py ingest path/to/some_file.pdf

# Ask a question
python cli.py ask "What does the document say about X?"

# Check index size / clear it
python cli.py status
python cli.py reset
```

## Web UI

```bash
python app.py
# or: uvicorn app:app --reload
```

Then open http://127.0.0.1:8000 — drop a document in the sidebar to ingest it,
then ask questions in the chat box. Answers stream in and cite their source file.

## How it works

1. **Ingest** (`rag/loaders.py`, `rag/chunking.py`) — documents are loaded, split
   into ~1000-character overlapping chunks on paragraph/sentence boundaries.
2. **Index** (`rag/store.py`) — chunks are embedded locally with
   sentence-transformers and stored in a persistent ChromaDB collection
   (`chroma_db/`, gitignored).
3. **Retrieve** (`rag/pipeline.py`) — a question is embedded the same way and
   matched against the index for the top-k most similar chunks.
4. **Generate** (`rag/generator.py`) — the retrieved chunks are placed in the
   system/user prompt and a Groq-hosted model (`llama-3.3-70b-versatile` by
   default, free tier) answers using only that context, citing sources.

## Configuration

All settings are environment variables (see `.env.example`), read via
`rag/config.py`: `GROQ_MODEL`, `EMBEDDING_MODEL`, `CHROMA_DIR`,
`COLLECTION_NAME`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`.

## Project layout

```
rag/
  config.py      settings
  loaders.py     .txt / .md / .pdf -> text
  chunking.py    text -> overlapping chunks
  store.py       ChromaDB wrapper (embed + upsert + query)
  generator.py   Groq LLM calls (sync + async streaming)
  pipeline.py    ties ingest/retrieve/generate together
cli.py           command-line interface
app.py           FastAPI web app
templates/       chat UI
data/documents/  drop files here to ingest via CLI
```
