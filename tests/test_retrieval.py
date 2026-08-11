from rag.retrieval import reciprocal_rank_fusion, tokenize


def test_item_ranked_top_in_both_lists_wins_overall():
    dense = ["a", "b", "c"]
    keyword = ["a", "c", "b"]

    fused = reciprocal_rank_fusion([dense, keyword])

    assert fused[0] == "a"


def test_item_only_in_one_list_is_still_included():
    dense = ["a", "b"]
    keyword = ["c"]

    fused = reciprocal_rank_fusion([dense, keyword])

    assert set(fused) == {"a", "b", "c"}


def test_item_appearing_in_multiple_lists_outranks_single_list_item():
    dense = ["a", "b"]
    keyword = ["b", "c"]

    fused = reciprocal_rank_fusion([dense, keyword])

    # "b" appears (rank 2 and rank 1) in both lists; "a" and "c" each appear once.
    assert fused.index("b") < fused.index("a")
    assert fused.index("b") < fused.index("c")


def test_single_ranking_preserves_order():
    fused = reciprocal_rank_fusion([["x", "y", "z"]])

    assert fused == ["x", "y", "z"]


def test_tokenize_lowercases_and_extracts_alphanumeric_words():
    assert tokenize("What Swift version is required?") == ["what", "swift", "version", "is", "required"]
