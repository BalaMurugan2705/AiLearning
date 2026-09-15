"""Slower than a typical unit test: builds a real embedding model and
ingests the 3 PDFs into a real (temp-dir) Chroma collection, same tradeoff
tests/test_store_filtering.py already makes for retrieval-behavior tests.
"""
import pytest

from agent.corpus import get_pipeline, search_docs_raw


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    persist_dir = str(tmp_path_factory.mktemp("week7_chroma"))
    return get_pipeline(persist_dir=persist_dir, collection_name="week7_test")


def test_ingestion_indexes_all_three_pdfs(pipeline):
    assert pipeline.document_count() > 0


def test_search_docs_finds_deprecation_language(pipeline):
    results = search_docs_raw(pipeline, "assignee deprecated issue", k=4)
    assert any("assignee" in r["text"].lower() for r in results)


def test_search_docs_finds_swagger_codegen_content(pipeline):
    results = search_docs_raw(pipeline, "Swagger Codegen CLI Maven group id", k=4)
    assert any("swagger" in r["metadata"].get("source_file", "").lower() for r in results)
