"""The labeling CLI, and the two properties that make it blind.

It imports nothing from judge.py's verdict data and refuses to run once a
judge run exists. Labeling after reading the judge's verdicts is not
validation -- it is agreeing with yourself with extra steps.
"""
import pytest

from eval.week6.label import (
    BlindnessError,
    build_labels_file,
    ensure_blind,
    render_case,
)

REC = {
    "case_id": "W6-07",
    "question": "What's the default retry backoff for Client.send()?",
    "mode": "version-ambiguity",
    "retrieved": [
        {"chunk_id": "v2:client:structural:2", "source_file": "v2/client.md", "text": "default 500 ms"},
        {"chunk_id": "v3:client:structural:2", "source_file": "v3/client.md", "text": "default 2000 ms"},
    ],
    "raw_output": "The default is 500 ms.",
}


def test_ensure_blind_allows_labeling_before_any_judge_run(tmp_path):
    assert ensure_blind([tmp_path / "judge_v1_run.json"], force=False) is True


def test_ensure_blind_refuses_once_a_judge_run_exists(tmp_path):
    run = tmp_path / "judge_v1_run.json"
    run.write_text("{}")
    with pytest.raises(BlindnessError, match="already been run"):
        ensure_blind([run], force=False)


def test_force_relabel_is_allowed_but_marks_the_file_as_not_blind(tmp_path):
    run = tmp_path / "judge_v1_run.json"
    run.write_text("{}")
    assert ensure_blind([run], force=True) is False


def test_render_case_shows_the_question_chunks_and_answer():
    text = render_case(REC, 1, 25)
    assert "1/25" in text
    assert "W6-07" in text
    assert "v2:client:structural:2" in text
    assert "The default is 500 ms." in text


def test_render_case_never_shows_the_mode_tag():
    """Knowing a case was filed under "version-ambiguity" tells the labeler
    what to look for and biases the label toward the taxonomy."""
    assert "version-ambiguity" not in render_case(REC, 1, 25)


def test_labels_file_records_the_criterion_and_the_answers_hash():
    rows = [{"case_id": "W6-07", "label": False, "seconds": 41, "note": "v2 number"}]
    out = build_labels_file("Would a developer act on this?", "abc123", rows, blind=True)
    assert out["criterion_text"] == "Would a developer act on this?"
    assert out["criterion_sha256"]
    assert out["answers_sha256"] == "abc123"
    assert out["blind"] is True
    assert out["labels"] == rows


def test_a_forced_relabel_is_self_incriminating_in_the_file():
    out = build_labels_file("c", "abc", [], blind=False)
    assert out["blind"] is False


def test_label_module_does_not_import_judge_verdicts():
    """Structural guarantee, not a promise: there is no code path by which a
    verdict could reach the labeler's screen."""
    import inspect

    import eval.week6.label as label

    source = inspect.getsource(label)
    assert "verdict" not in source.lower()
    assert "run_judge" not in source
