import json
from pathlib import Path

QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "eval" / "week7" / "questions.json"


def _load():
    return json.loads(QUESTIONS_PATH.read_text())


def test_exactly_ten_questions():
    assert len(_load()) == 10


def test_every_question_has_required_fields():
    for q in _load():
        assert set(q.keys()) == {"id", "question", "expected_fragment", "needs_chain"}
        assert isinstance(q["needs_chain"], bool)


def test_at_least_three_questions_need_chaining():
    assert sum(1 for q in _load() if q["needs_chain"]) >= 3


def test_ids_are_unique():
    ids = [q["id"] for q in _load()]
    assert len(ids) == len(set(ids))
