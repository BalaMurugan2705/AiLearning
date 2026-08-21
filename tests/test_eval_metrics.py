"""Scoring rules for the two hit metrics.

Metric A (pre-registered): a top-5 chunk from the expected page whose text
contains the answer span.

Metric B (added after A saturated at 8/8 for both strategies): the same, plus
every support span present in that same chunk — which for a parameter-table
question means the row is still attached to its header row.
"""
from eval.metrics import score_question


def _result(rank, text, source_file="v3/client.md", chunk_id=None):
    return {
        "rank": rank,
        "chunk_id": chunk_id or f"v3:client:structural:{rank}",
        "text": text,
        "metadata": {"source_file": source_file},
    }


HEADER = "| Parameter | Type | Default | Required | Description |"
ROW = "| `retry_backoff_ms` | `int` | `2000` | no | Base delay. |"
CODE_FRAGMENT = 'client.send(channel="x", retry_backoff_ms=2000)'

QUESTION = {
    "page": "v3/client.md",
    "answer_span": "2000",
    "support_spans": ["`retry_backoff_ms`", HEADER],
}


def test_metric_a_counts_a_chunk_from_the_right_page_containing_the_span():
    score = score_question([_result(0, ROW)], QUESTION)
    assert score["hit"] is True
    assert score["hit_rank"] == 1


def test_metric_a_ignores_the_span_on_the_wrong_page():
    score = score_question([_result(0, ROW, source_file="v2/client.md")], QUESTION)
    assert score["hit"] is False
    assert score["hit_rank"] is None


def test_metric_b_rejects_a_code_fragment_that_merely_mentions_the_value():
    """The exact false positive found in the first run: a caller-supplied
    argument in an example is not a statement of the default."""
    score = score_question([_result(0, CODE_FRAGMENT)], QUESTION)
    assert score["hit"] is True, "metric A still counts it, by design"
    assert score["supported_hit"] is False


def test_metric_b_accepts_a_row_still_attached_to_its_header():
    score = score_question([_result(0, f"{HEADER}\n|---|\n{ROW}")], QUESTION)
    assert score["supported_hit"] is True
    assert score["supported_hit_rank"] == 1


def test_metric_b_rejects_a_row_severed_from_its_header():
    score = score_question([_result(0, ROW)], QUESTION)
    assert score["hit"] is True
    assert score["supported_hit"] is False


def test_metric_b_requires_all_support_spans_in_the_same_chunk():
    """Header in one chunk and the row in another is exactly the failure the
    structure-aware chunker is supposed to prevent."""
    results = [_result(0, HEADER), _result(1, ROW)]
    score = score_question(results, QUESTION)
    assert score["supported_hit"] is False


def test_metrics_agree_when_a_question_has_no_support_spans():
    prose = {"page": "v3/auth.md", "answer_span": "3600 seconds", "support_spans": []}
    results = [_result(0, "A token is valid for 3600 seconds.", source_file="v3/auth.md")]
    score = score_question(results, prose)
    assert score["hit"] is True
    assert score["supported_hit"] is True


def test_ranks_report_the_first_qualifying_chunk():
    results = [
        _result(0, "unrelated text"),
        _result(1, CODE_FRAGMENT),
        _result(2, f"{HEADER}\n|---|\n{ROW}"),
    ]
    score = score_question(results, QUESTION)
    assert score["hit_rank"] == 2
    assert score["supported_hit_rank"] == 3
