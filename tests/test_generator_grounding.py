"""Refusal gate and citation verification (Week 3 requirement 5).

The 20-point citation criterion says a citation must resolve to a real
chunk_id and the cited chunk must actually contain the claim. These tests
pin both halves, plus the gate that refuses before the model is ever called.
"""
import pytest

from rag.config import REFUSAL_MESSAGE
from rag.generator import (
    SYSTEM_PROMPT,
    answer_question,
    build_context,
    extract_citations,
    should_refuse,
    verify_citations,
)


def _chunk(chunk_id="v3:client:structural:7", distance=0.30, text="The default is 2000 ms."):
    return {
        "chunk_id": chunk_id,
        "text": text,
        "dense_distance": distance,
        "metadata": {
            "source_file": "v3/client.md",
            "anchor": "#parameters",
            "heading_path": "Client.send() > Parameters",
        },
    }


def test_context_labels_each_chunk_with_its_id_and_anchor():
    context = build_context([_chunk()])
    assert "[chunk: v3:client:structural:7 | v3/client.md#parameters]" in context


def test_context_omits_anchor_when_chunk_has_none():
    chunk = _chunk()
    chunk["metadata"]["anchor"] = ""
    context = build_context([chunk])
    assert "[chunk: v3:client:structural:7 | v3/client.md]" in context


def test_gate_refuses_when_nothing_was_retrieved():
    assert should_refuse([], threshold=0.6) is True


def test_gate_refuses_when_best_match_is_beyond_the_threshold():
    assert should_refuse([_chunk(distance=0.85)], threshold=0.6) is True


def test_gate_allows_when_a_chunk_is_within_the_threshold():
    assert should_refuse([_chunk(distance=0.31)], threshold=0.6) is False


def test_gate_uses_the_closest_chunk_not_the_first():
    chunks = [_chunk(distance=0.90), _chunk(chunk_id="other", distance=0.20)]
    assert should_refuse(chunks, threshold=0.6) is False


def test_gated_refusal_never_calls_the_model(monkeypatch):
    """A deterministic refusal must not depend on the LLM's cooperation, and
    must not spend a request to produce it."""
    def explode():
        raise AssertionError("the model must not be called when the gate refuses")

    monkeypatch.setattr("rag.generator._get_client", explode)
    answer = answer_question("anything", [_chunk(distance=0.99)], threshold=0.6)
    assert answer == REFUSAL_MESSAGE


def test_extract_citations_finds_every_cited_id():
    answer = (
        "The default is 2000 ms [chunk: v3:client:structural:7]. "
        "Retries are exponential [chunk: v3:client:structural:8]."
    )
    assert extract_citations(answer) == [
        "v3:client:structural:7",
        "v3:client:structural:8",
    ]


def test_extract_citations_tolerates_the_page_suffix():
    answer = "Signed with HMAC-SHA256 [chunk: v3:webhooks:structural:1 | v3/webhooks.md#signature-verification]."
    assert extract_citations(answer) == ["v3:webhooks:structural:1"]


def test_verification_passes_when_every_citation_resolves():
    answer = "The default is 2000 ms [chunk: v3:client:structural:7]."
    report = verify_citations(answer, [_chunk()])
    assert report["ok"] is True
    assert report["unresolvable"] == []


def test_verification_flags_a_fabricated_chunk_id():
    answer = "The limit is 900 [chunk: v3:client:structural:999]."
    report = verify_citations(answer, [_chunk()])
    assert report["ok"] is False
    assert report["unresolvable"] == ["v3:client:structural:999"]


def test_verification_flags_an_answer_with_no_citations_at_all():
    report = verify_citations("The default is 2000 ms.", [_chunk()])
    assert report["ok"] is False
    assert report["cited"] == []


def test_verification_confirms_the_cited_chunk_contains_the_claim():
    answer = "The default is 2000 ms [chunk: v3:client:structural:7]."
    report = verify_citations(answer, [_chunk()], expected_span="2000")
    assert report["span_supported"] is True


def test_verification_reports_a_citation_that_does_not_contain_the_claim():
    """Resolving is not enough. A real chunk_id attached to a claim that chunk
    does not make is exactly what the grader checks for by hand."""
    answer = "The maximum is 86400000 [chunk: v3:client:structural:7]."
    report = verify_citations(answer, [_chunk(text="The default is 2000 ms.")], expected_span="86400000")
    assert report["span_supported"] is False


def test_system_prompt_forces_refusal_rather_than_suggesting_it():
    lowered = SYSTEM_PROMPT.lower()
    assert REFUSAL_MESSAGE.lower() in lowered
    for hedge in ("best judgement", "best judgment", "if you are unsure, try", "general knowledge"):
        assert hedge not in lowered, f"prompt still contains an escape hatch: {hedge!r}"


def test_system_prompt_requires_chunk_level_citations():
    assert "[chunk:" in SYSTEM_PROMPT
