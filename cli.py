#!/usr/bin/env python3
"""Command-line interface for the RAG app.

Usage:
    python cli.py ingest <path>        Ingest a file or directory (.txt, .md, .pdf)
    python cli.py search "<question>"  Retrieve only — no LLM call, shows scores
    python cli.py ask "<question>"     Ask a question against the indexed documents
    python cli.py reset                Clear the vector index
    python cli.py status               Show how many chunks are indexed
"""
import argparse
import sys

from rag.chunking import BASELINE, STRUCTURAL
from rag.config import GROQ_API_KEY, TOP_K
from rag.generator import sources_from_chunks, stream_answer_text
from rag.pipeline import RAGPipeline


def _where(args: argparse.Namespace) -> dict | None:
    return {"sdk_version": args.sdk_version} if args.sdk_version else None


def cmd_ingest(pipeline: RAGPipeline, args: argparse.Namespace) -> None:
    result = pipeline.ingest_path(args.path)
    if result["files_ingested"] == 0:
        print(f"No supported documents found under: {args.path}")
        print("Supported types: .txt, .md, .pdf")
        return
    print(f"Ingested {result['files_ingested']} file(s), {result['chunks_ingested']} chunk(s).")
    for source_file in result["source_files"]:
        print(f"  - {source_file}")
    print(f"Index '{pipeline.strategy}' now has {pipeline.document_count()} chunk(s) total.")


def cmd_search(pipeline: RAGPipeline, args: argparse.Namespace) -> None:
    """Retrieval only. No generation, so nothing here can invent an answer."""
    if pipeline.document_count() == 0:
        print("The index is empty. Run 'python cli.py ingest <path>' first.")
        return

    results = pipeline.retrieve(args.question, k=args.k, where=_where(args))
    if not results:
        print("No results.")
        return

    print(f"strategy={pipeline.strategy}  k={args.k}  filter={_where(args) or 'none'}\n")
    for result in results:
        metadata = result["metadata"]
        dense = result["dense_distance"]
        bm25 = result["bm25_score"]
        print(
            f"#{result['rank'] + 1}  {result['chunk_id']}\n"
            f"    {metadata.get('source_file', '?')}{metadata.get('anchor', '')}"
            f"  [{metadata.get('heading_path', '')}]\n"
            f"    rrf={result['rrf_score']:.5f}  "
            f"cosine={'—' if dense is None else f'{dense:.4f}'}  "
            f"bm25={'—' if bm25 is None else f'{bm25:.3f}'}\n"
            f"    {result['text'][:160].replace(chr(10), ' ')}...\n"
        )


def cmd_ask(pipeline: RAGPipeline, args: argparse.Namespace) -> None:
    if pipeline.document_count() == 0:
        print("The index is empty. Run 'python cli.py ingest <path>' first.")
        return

    chunks = pipeline.retrieve(args.question, k=args.k, where=_where(args))
    print("Answer:\n")
    for delta in stream_answer_text(args.question, chunks):
        print(delta, end="", flush=True)
    print("\n")

    sources = sources_from_chunks(chunks)
    if sources:
        print("Sources: " + ", ".join(sources))


def cmd_reset(pipeline: RAGPipeline, args: argparse.Namespace) -> None:
    pipeline.reset()
    print(f"Index '{pipeline.strategy}' cleared.")


def cmd_status(pipeline: RAGPipeline, args: argparse.Namespace) -> None:
    print(f"{pipeline.document_count()} chunk(s) indexed in '{pipeline.strategy}'.")


def _add_strategy(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--strategy",
        choices=[STRUCTURAL, BASELINE],
        default=STRUCTURAL,
        help="Which chunking strategy's index to use (default: structural)",
    )


def _add_retrieval_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--k", type=int, default=TOP_K, help="Number of chunks to retrieve")
    parser.add_argument(
        "--sdk-version",
        dest="sdk_version",
        default=None,
        help="Restrict retrieval to one sdk_version, e.g. v3",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG CLI — ingest documents and ask questions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ingest = subparsers.add_parser("ingest", help="Ingest a file or directory")
    p_ingest.add_argument("path", help="Path to a document or a directory of documents")
    p_ingest.add_argument(
        "--require-front-matter",
        action="store_true",
        help="Fail the ingest if a page has no front matter block",
    )
    _add_strategy(p_ingest)
    p_ingest.set_defaults(func=cmd_ingest)

    p_search = subparsers.add_parser("search", help="Retrieve only, without calling the LLM")
    p_search.add_argument("question", help="Your query")
    _add_retrieval_flags(p_search)
    _add_strategy(p_search)
    p_search.set_defaults(func=cmd_search)

    p_ask = subparsers.add_parser("ask", help="Ask a question")
    p_ask.add_argument("question", help="Your question")
    _add_retrieval_flags(p_ask)
    _add_strategy(p_ask)
    p_ask.set_defaults(func=cmd_ask)

    p_reset = subparsers.add_parser("reset", help="Clear the vector index")
    _add_strategy(p_reset)
    p_reset.set_defaults(func=cmd_reset)

    p_status = subparsers.add_parser("status", help="Show index size")
    _add_strategy(p_status)
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()

    if not GROQ_API_KEY and args.command == "ask":
        print("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    pipeline = RAGPipeline(
        strategy=args.strategy,
        require_front_matter=getattr(args, "require_front_matter", False),
    )
    args.func(pipeline, args)


if __name__ == "__main__":
    main()
