#!/usr/bin/env python3
"""Command-line interface for the RAG app.

Usage:
    python cli.py ingest <path>        Ingest a file or directory (.txt, .md, .pdf)
    python cli.py ask "<question>"     Ask a question against the indexed documents
    python cli.py reset                Clear the vector index
    python cli.py status               Show how many chunks are indexed
"""
import argparse
import sys

from rag.config import GROQ_API_KEY, TOP_K
from rag.generator import sources_from_chunks, stream_answer_text
from rag.pipeline import RAGPipeline


def cmd_ingest(pipeline: RAGPipeline, args: argparse.Namespace) -> None:
    result = pipeline.ingest_path(args.path)
    if result["files_ingested"] == 0:
        print(f"No supported documents found under: {args.path}")
        print("Supported types: .txt, .md, .pdf")
        return
    print(f"Ingested {result['files_ingested']} file(s), {result['chunks_ingested']} chunk(s).")
    print(f"Index now has {pipeline.document_count()} chunk(s) total.")


def cmd_ask(pipeline: RAGPipeline, args: argparse.Namespace) -> None:
    if pipeline.document_count() == 0:
        print("The index is empty. Run 'python cli.py ingest <path>' first.")
        return

    chunks = pipeline.retrieve(args.question, k=args.k)
    print("Answer:\n")
    for delta in stream_answer_text(args.question, chunks):
        print(delta, end="", flush=True)
    print("\n")

    sources = sources_from_chunks(chunks)
    if sources:
        print("Sources: " + ", ".join(sources))


def cmd_reset(pipeline: RAGPipeline, args: argparse.Namespace) -> None:
    pipeline.reset()
    print("Index cleared.")


def cmd_status(pipeline: RAGPipeline, args: argparse.Namespace) -> None:
    print(f"{pipeline.document_count()} chunk(s) indexed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG CLI — ingest documents and ask questions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ingest = subparsers.add_parser("ingest", help="Ingest a file or directory")
    p_ingest.add_argument("path", help="Path to a document or a directory of documents")
    p_ingest.set_defaults(func=cmd_ingest)

    p_ask = subparsers.add_parser("ask", help="Ask a question")
    p_ask.add_argument("question", help="Your question")
    p_ask.add_argument("--k", type=int, default=TOP_K, help="Number of chunks to retrieve")
    p_ask.set_defaults(func=cmd_ask)

    p_reset = subparsers.add_parser("reset", help="Clear the vector index")
    p_reset.set_defaults(func=cmd_reset)

    p_status = subparsers.add_parser("status", help="Show index size")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()

    if not GROQ_API_KEY and args.command == "ask":
        print("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    pipeline = RAGPipeline()
    args.func(pipeline, args)


if __name__ == "__main__":
    main()
