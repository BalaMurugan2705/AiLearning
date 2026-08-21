from rag.retrieval import RRF_K, fuse_with_scores, reciprocal_rank_fusion


def test_returns_id_score_pairs_sorted_by_score():
    fused = fuse_with_scores([["a", "b", "c"], ["a", "c", "b"]])
    assert fused[0][0] == "a"
    assert all(isinstance(score, float) for _, score in fused)
    scores = [score for _, score in fused]
    assert scores == sorted(scores, reverse=True)


def test_items_at_mirrored_ranks_score_identically():
    """b is ranked 2nd then 3rd, c is 3rd then 2nd, so their RRF scores are
    equal and their relative order is arbitrary. Asserting one ordering here
    would be asserting sort stability, not retrieval behaviour."""
    fused = dict(fuse_with_scores([["a", "b", "c"], ["a", "c", "b"]]))
    assert fused["b"] == fused["c"]
    assert fused["a"] > fused["b"]


def test_score_is_the_sum_of_reciprocal_ranks():
    fused = dict(fuse_with_scores([["a", "b"], ["b", "a"]]))
    expected = 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 2)
    assert fused["a"] == expected
    assert fused["b"] == expected


def test_item_in_one_ranking_scores_lower_than_item_in_both():
    fused = dict(fuse_with_scores([["a", "b"], ["b", "c"]]))
    assert fused["b"] > fused["a"]
    assert fused["b"] > fused["c"]


def test_plain_fusion_still_returns_bare_ids():
    """Regression guard: the id-only API is used elsewhere and must not change."""
    assert reciprocal_rank_fusion([["x", "y", "z"]]) == ["x", "y", "z"]
