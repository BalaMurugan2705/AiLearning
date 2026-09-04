"""Integrity of the 25-case eval set.

The mode tags are the Week 5 taxonomy names verbatim, so the two write-ups
line up. Regression cases are lifted out of traces.jsonl by script rather
than retyped, which is what makes "replayed verbatim" checkable instead of a
claim.
"""
from eval.week6.build_cases import MODES, case_from_trace, load_cases
from rag.tracing import load_traces

TRACE = {
    "trace_id": "b84fe53eb006",
    "question": "What's the default retry backoff for Client.send()?",
    "strategy": "structural",
    "k": 4,
    "where": None,
    "rerank": False,
    "model": "openai/gpt-oss-120b",
    "model_params": {"max_tokens": 2048},
    "retrieved": [
        {
            "chunk_id": "v2:client:structural:3",
            "dense_distance": 0.5132670402526855,
            "bm25_score": 19.004,
            "rrf_score": 0.0327,
            "rerank_score": None,
        }
    ],
}


def test_case_from_trace_copies_every_execution_parameter():
    case = case_from_trace(TRACE, "W6-07", "version-ambiguity", True, "note")
    assert case["question"] == TRACE["question"]
    assert case["retrieval"] == {"k": 4, "where": None, "strategy": "structural", "rerank": False}
    assert case["generation"] == {"model": "openai/gpt-oss-120b", "model_params": {"max_tokens": 2048}}
    assert case["origin"] == {"kind": "replay", "trace_id": "b84fe53eb006"}


def test_case_from_trace_carries_the_logged_retrieval_scores():
    """Not just the chunk ids. should_refuse() treats a chunk with no
    dense_distance as no evidence, so a case that kept only the ids would
    answer with the refusal string instead of reproducing its failure -- which
    would quietly void every regression case in the set."""
    case = case_from_trace(TRACE, "W6-07", "version-ambiguity", True, "note")
    assert case["replay_retrieved"][0]["chunk_id"] == "v2:client:structural:3"
    assert case["replay_retrieved"][0]["dense_distance"] == 0.5132670402526855
    assert case["replay_retrieved"][0]["bm25_score"] == 19.004


def test_every_replay_case_has_at_least_one_scored_chunk():
    for case in load_cases():
        if case["origin"]["kind"] != "replay":
            continue
        scored = [
            r for r in case["replay_retrieved"] if r["dense_distance"] is not None
        ]
        assert scored, f"{case['case_id']} would refuse for lack of dense scores"


def test_there_are_at_least_25_cases():
    assert len(load_cases()) >= 25


def test_every_case_has_exactly_one_known_mode():
    for case in load_cases():
        assert case["mode"] in MODES, case["case_id"]


def test_every_mode_is_represented():
    used = {case["mode"] for case in load_cases()}
    assert used == set(MODES)


def test_case_ids_are_unique():
    ids = [case["case_id"] for case in load_cases()]
    assert len(ids) == len(set(ids))


def test_at_least_two_cases_are_real_replayed_regressions():
    replays = [c for c in load_cases() if c["origin"]["kind"] == "replay"]
    assert len(replays) >= 2


def test_every_replay_case_matches_its_trace_verbatim():
    """This is what "replayed verbatim" means: not a paraphrase of a failure
    we remember, but the exact question and parameters that were logged."""
    traces = {t["trace_id"]: t for t in load_traces()}
    for case in load_cases():
        if case["origin"]["kind"] != "replay":
            continue
        trace = traces[case["origin"]["trace_id"]]
        assert case["question"] == trace["question"], case["case_id"]
        assert case["retrieval"]["k"] == trace["k"], case["case_id"]
        assert case["retrieval"]["where"] == trace["where"], case["case_id"]
        assert case["retrieval"]["strategy"] == trace["strategy"], case["case_id"]
        assert case["retrieval"]["rerank"] == trace["rerank"], case["case_id"]
        assert case["generation"]["model"] == trace["model"], case["case_id"]


def test_authored_cases_declare_what_they_were_based_on():
    for case in load_cases():
        if case["origin"]["kind"] == "authored":
            assert case["origin"]["basis"], case["case_id"]


def test_version_ambiguity_cases_are_all_version_sensitive():
    """sdk_version_intent "unspecified" does not mean the version does not
    matter -- it is the bucket where stating it matters most."""
    for case in load_cases():
        if case["mode"] == "version-ambiguity":
            assert case["version_sensitive"] is True, case["case_id"]
