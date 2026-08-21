"""Integration tests for metadata filtering and score reporting.

These run against a real ChromaDB collection and the real embedding model,
because the behaviour under test is precisely the interaction between the
dense leg, the BM25 leg and the filter. Mocking either leg would test the
mock instead of the bug the filter exists to fix.
"""
import pytest

from rag.store import VectorStore

V3_TEXT = (
    "Client.send() parameters. The retry_backoff_ms parameter has a default of 2000 "
    "milliseconds and retries use exponential backoff."
)
V2_TEXT = (
    "Client.send() default retry backoff. The default retry backoff for Client.send() "
    "is 500 ms and retries use a fixed delay."
)

QUERY = "default retry backoff for Client.send()"


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    s = VectorStore(
        persist_dir=str(tmp_path_factory.mktemp("chroma")),
        collection_name="filter_test",
    )
    s.add_texts(
        texts=[V3_TEXT, V2_TEXT],
        metadatas=[
            {"sdk_version": "v3", "source_file": "v3/client.md", "page_id": "client"},
            {"sdk_version": "v2", "source_file": "v2/client.md", "page_id": "client"},
        ],
        ids=["v3:client:structural:0", "v2:client:structural:0"],
    )
    return s


def test_unfiltered_query_can_return_both_versions(store):
    results = store.query(QUERY, k=5)
    versions = {r["metadata"]["sdk_version"] for r in results}
    assert versions == {"v2", "v3"}


def test_filter_excludes_the_other_version_from_both_legs(store):
    """The v2 text is a strong lexical match for this query, so if BM25
    ignored the filter a v2 chunk would still surface through fusion."""
    results = store.query(QUERY, k=5, where={"sdk_version": "v3"})
    assert results
    assert all(r["metadata"]["sdk_version"] == "v3" for r in results)


def test_results_carry_the_chunk_id(store):
    results = store.query(QUERY, k=5)
    assert all(r["chunk_id"] for r in results)
    assert "v3:client:structural:0" in {r["chunk_id"] for r in results}


def test_results_carry_real_scores_not_rank_positions(store):
    results = store.query(QUERY, k=5)
    assert all(isinstance(r["rrf_score"], float) and r["rrf_score"] > 0 for r in results)
    dense = [r["dense_distance"] for r in results if r["dense_distance"] is not None]
    assert dense, "at least one result should carry a raw dense distance"
    assert all(isinstance(d, float) for d in dense)


def test_dense_distance_is_cosine_and_therefore_bounded(store):
    """Chroma defaults to squared L2, which has no interpretable scale. The
    refusal threshold needs cosine, which is bounded in [0, 2]."""
    results = store.query(QUERY, k=5)
    dense = [r["dense_distance"] for r in results if r["dense_distance"] is not None]
    assert all(0.0 <= d <= 2.0 for d in dense), dense


def test_all_ids_exposes_what_is_indexed(store):
    """Requirement 6 says index only the 6 new pages. Snapshotting ids before
    and after turns that claim into a check."""
    assert store.all_ids() == {"v3:client:structural:0", "v2:client:structural:0"}


def test_get_by_id_resolves_a_citation_back_to_its_chunk(store):
    resolved = store.get_by_id("v3:client:structural:0")
    assert resolved is not None
    assert "2000" in resolved["text"]
    assert store.get_by_id("v3:client:structural:404") is None


def test_a_closer_match_has_a_smaller_dense_distance(store):
    results = store.query("exponential backoff retry_backoff_ms default 2000", k=5)
    by_id = {r["chunk_id"]: r for r in results}
    v3, v2 = by_id["v3:client:structural:0"], by_id["v2:client:structural:0"]
    assert v3["dense_distance"] < v2["dense_distance"]
