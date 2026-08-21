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

# Retrieve only — no LLM call, prints chunk_ids and all three scores
python cli.py search "default retry backoff for Client.send()" --k 5

# Restrict retrieval to one documentation version
python cli.py search "default retry backoff" --k 5 --sdk-version v3

# Work against the baseline chunker's index instead of the structure-aware one
python cli.py search "default retry backoff" --strategy baseline

# Check index size / clear it
python cli.py status
python cli.py reset
```

`search` never calls the LLM, so nothing it prints can be invented. Every
command takes `--strategy` (`structural`, the default, or `baseline`), which
selects the collection to read or write.

Re-ingesting a file (same path) always replaces that file's chunks in the
index, so editing a doc and re-running `ingest` never leaves stale content
behind. Simply deleting a file from `data/documents/` does *not* remove it
from the index on its own — use `reset` if you need the index to fully match
what's currently on disk.

## Web UI

```bash
python app.py
# or: uvicorn app:app --reload
```

Then open http://127.0.0.1:8000 — drop a document in the sidebar to ingest it,
then ask questions in the chat box. `/api/ask` returns the full answer as a
single JSON response (not streamed); inline `[source: ...]` citations are
hidden from the rendered answer, and used sources are listed in a footer line
below it instead.

## How it works

1. **Ingest** (`rag/loaders.py`, `rag/chunking.py`) — documents are loaded and
   split into chunks. Markdown (`.md`) is chunked structurally: one chunk per
   header section (e.g. one per SDK method) tagged with its heading path
   (`API Reference > createUser()`), with fenced code blocks always kept
   whole and attached to their explanation, never split mid-block. A
   paragraph whose first line is a bare bold label (`**Minimum
   Requirements:**` followed by its list) becomes its own chunk too, instead
   of merging with unrelated sibling fact-lists under the same header.
   Oversized sections fall back to ~1000-character overlapping sub-chunks on
   paragraph/sentence boundaries. `.txt` and `.pdf` (no reliable header
   structure) always use that paragraph/sentence chunker directly.
2. **Index** (`rag/store.py`) — chunks are embedded locally with
   sentence-transformers and stored in a persistent ChromaDB collection
   (`chroma_db/`, gitignored), alongside an in-memory BM25 keyword index
   (`rag/retrieval.py`) rebuilt lazily whenever the collection changes.
3. **Retrieve** (`rag/pipeline.py`, `rag/store.py`) — a question is run
   through both dense (embedding) search and BM25 keyword search, and the
   two rankings are merged via Reciprocal Rank Fusion before taking the
   top-k. This surfaces exact technical terms (version numbers, method
   names) that pure semantic search alone can under-rank in favor of a more
   generic-sounding chunk.
4. **Generate** (`rag/generator.py`) — the retrieved chunks are placed in the
   system/user prompt and a Groq-hosted model (`llama-3.3-70b-versatile` by
   default, free tier) answers using only that context. Refusal is enforced in
   two independent layers: a retrieval gate that refuses before any model call
   when the closest chunk's raw cosine distance exceeds a calibrated threshold,
   and a system prompt that mandates an exact refusal sentence with no
   "use your best judgement" escape hatch. Every factual sentence must carry a
   `[chunk: <chunk_id>]` citation, and `verify_citations()` checks each cited
   id was actually retrieved — a fabricated id is a hallucinated citation.

## Metadata and chunk ids

Documents may carry front matter, which is parsed strictly by
`rag/frontmatter.py` (deliberately not YAML: `required: no` would resolve to
boolean `False` under YAML 1.1):

```markdown
---
page_id: client
sdk_version: v3
page_type: reference
---
```

Every chunk is tagged with `source_file`, `page_id`, `sdk_version`,
`page_type`, `strategy`, `heading_path` and `anchor`. `source_file` is derived
from the path and is therefore never absent, so `v2/client.md` and
`v3/client.md` stay distinguishable. Chunk ids are readable rather than hashed
— `v3:client:structural:7` — so a citation can be resolved by hand.

Retrieval accepts a `where` filter (e.g. `{"sdk_version": "v3"}`) applied to
**both** the dense and BM25 legs. Filtering only the dense leg would let an
excluded chunk re-enter the results through the keyword leg.

## Configuration

All settings are environment variables (see `.env.example`), read via
`rag/config.py`: `GROQ_MODEL`, `EMBEDDING_MODEL`, `CHROMA_DIR`,
`COLLECTION_NAME`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`.

## Project layout

```
rag/
  config.py       settings, collection names, refusal message + threshold
  frontmatter.py  strict `key: value` front matter parsing and validation
  loaders.py      .txt / .md / .pdf -> text
  chunking.py     text -> chunks, under a baseline or structure-aware strategy
  store.py        ChromaDB wrapper (embed + upsert + filtered hybrid query)
  generator.py    Groq LLM calls, refusal gate, citation verification
  pipeline.py     ties ingest/retrieve/generate together
eval/
  questions.json  the 8 eval + 3 out-of-corpus + 5 calibration questions
  metrics.py      hit scoring under both metrics
  run_eval.py     builds both indexes and produces every artifact
  report.py       renders results.md from raw/artifacts.json
  raw/            machine-readable output of the last run
cli.py            command-line interface
app.py            FastAPI web app
templates/        chat UI
data/documents/   v2/ and v3/ SDK reference corpus
tests/            pytest suite
results.md        generated write-up — do not edit by hand
```

Run tests with `pytest` (`pip install pytest` / already in `requirements.txt` under the dev section).

## Week 3 evaluation

```bash
python -m eval.run_eval
```

Builds one index per chunking strategy, seeds the v2 pages as pre-existing
state, ingests only the 6 new v3 reference pages, runs all 8 questions
search-only against both strategies, searches for a query where the
`sdk_version` filter changes top-1, calibrates the refusal threshold on
held-out questions, then generates 3 cited answers and 3 refusals. It writes
`eval/raw/artifacts.json` and renders `results.md` from it, so the write-up and
the measured data cannot disagree.

Retrieval measurement needs no API key. The generation section is skipped with
a notice when `GROQ_API_KEY` is unset and filled in on a later run.

`results.md` is generated. Edit `eval/report.py` and re-run, never the
markdown.
