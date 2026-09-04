"""The frozen 25-answer snapshot.

Answers are generated ONCE and re-scored forever after. If they regenerated
per run, the 25 hand labels would silently decay and the
agreement_before -> agreement_after delta would mix judge changes with answer
drift, which would make the headline number of the whole week meaningless.
"""
import json

from eval.week6.snapshot import build_snapshot, canonical_sha256

CASES = [
    {
        "case_id": "W6-01",
        "question": "What is the default retry backoff?",
        "mode": "version-ambiguity",
        "origin": {"kind": "replay", "trace_id": "b84fe53eb006"},
        "version_sensitive": True,
        "sdk_version_intent": "unspecified",
        "retrieval": {"k": 4, "where": None, "strategy": "structural", "rerank": False},
        "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}},
        "replay_retrieved": [
            {
                "chunk_id": "v2:client:structural:2",
                "dense_distance": 0.51,
                "bm25_score": 19.0,
                "rrf_score": 0.0327,
                "rerank_score": None,
            }
        ],
        "notes": "",
    },
    {
        "case_id": "W6-02",
        "question": "Which error code means the token expired?",
        "mode": "clean",
        "origin": {"kind": "authored", "basis": "golden_set:Q3"},
        "version_sensitive": True,
        "sdk_version_intent": "v3",
        "retrieval": {"k": 4, "where": None, "strategy": "structural", "rerank": False},
        "generation": {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}},
        "replay_retrieved": None,
        "notes": "",
    },
]


def _resolve(case):
    return [
        {
            "chunk_id": "v3:errors:structural:1",
            "rank": 0,
            "text": "AUTH_TOKEN_EXPIRED means the bearer token is past its expiry.",
            "dense_distance": 0.2,
            "bm25_score": 9.0,
            "rrf_score": 0.03,
            "rerank_score": None,
            "metadata": {"source_file": "v3/errors.md", "sdk_version": "v3", "heading_path": "Errors"},
        }
    ]


def _answer(question, chunks, max_tokens, model):
    return f"answer to {question} [chunk: {chunks[0]['chunk_id']}]"


def test_snapshot_has_one_entry_per_case_carrying_its_mode():
    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)
    assert [a["case_id"] for a in snap["answers"]] == ["W6-01", "W6-02"]
    assert snap["answers"][0]["mode"] == "version-ambiguity"


def test_snapshot_records_the_retrieved_chunks_and_the_model_used():
    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)
    entry = snap["answers"][0]
    assert entry["retrieved"][0]["chunk_id"] == "v3:errors:structural:1"
    assert entry["model"] == "openai/gpt-oss-120b"
    assert entry["model_params"] == {"max_tokens": 2048}


def test_snapshot_flags_a_refusal():
    def refuse(question, chunks, max_tokens, model):
        return "I cannot answer that from the indexed documentation."

    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=refuse)
    assert snap["answers"][0]["refused"] is True


def test_answers_sha256_is_the_anchor_every_later_artifact_quotes():
    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)
    assert snap["answers_sha256"] == canonical_sha256(snap["answers"])


def test_answers_sha256_changes_when_any_answer_text_changes():
    a = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)

    def other(question, chunks, max_tokens, model):
        return "different text"

    b = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=other)
    assert a["answers_sha256"] != b["answers_sha256"]


def test_canonical_sha256_ignores_key_order():
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


def test_snapshot_is_json_serialisable():
    snap = build_snapshot(CASES, resolve_fn=_resolve, answer_fn=_answer)
    json.dumps(snap)
