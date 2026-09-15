import pytest

from eval.week7.golden_questions import load_golden_set


@pytest.mark.parametrize("level", ["easy", "medium", "hard"])
def test_each_level_has_fifteen_questions(level):
    assert len(load_golden_set(level)) == 15


@pytest.mark.parametrize("level", ["easy", "medium", "hard"])
def test_each_level_has_exactly_three_negative_cases(level):
    questions = load_golden_set(level)
    negatives = [q for q in questions if q["is_negative_case"]]
    assert len(negatives) == 3
    for q in negatives:
        assert q["expected_fragment"] is None


@pytest.mark.parametrize("level", ["easy", "medium", "hard"])
def test_every_positive_question_has_a_fragment(level):
    for q in load_golden_set(level):
        if not q["is_negative_case"]:
            assert q["expected_fragment"]


def test_hard_set_is_mostly_chain_questions():
    questions = load_golden_set("hard")
    chain_count = sum(1 for q in questions if q["needs_chain"])
    # 12 non-negative hard questions are all cross-version/cross-file
    # comparisons by construction; the 3 negative ones are not chains.
    assert chain_count == 12


def test_ids_are_unique_and_namespaced_by_level():
    questions = load_golden_set("easy")
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("easy-") for i in ids)
