"""The blind protocol, enforced in code.

The rubric scores the ORDER: 25 hand labels must provably predate the judge
run, and no ordering evidence means zero regardless of the numbers. So the
judge refuses to run against labels that are not committed, and every run
records the labels' commit hash and sha256 -- a hash that could only exist if
the labels were committed first.
"""
import json
import subprocess

import pytest

from eval.week6.judge import (
    OrderingError,
    build_judge_messages,
    parse_verdict,
    require_committed_labels,
    run_judge,
    sha256_file,
)


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    return tmp_path


def test_parse_verdict_reads_the_strict_contract():
    assert parse_verdict("VERDICT: PASS\nREASON: correct for v3") == ("PASS", "correct for v3")


def test_parse_verdict_reads_a_fail():
    assert parse_verdict("VERDICT: FAIL\nREASON: gives the v2 number")[0] == "FAIL"


def test_parse_verdict_refuses_to_guess_at_unparseable_output():
    """Coercing a rambling reply into PASS would silently invent agreement."""
    assert parse_verdict("I think this answer is pretty good overall!") == ("UNPARSED", "")


def test_parse_verdict_rejects_a_numeric_score():
    assert parse_verdict("SCORE: 7/10")[0] == "UNPARSED"


def test_guard_rejects_labels_that_were_never_committed(repo):
    labels = repo / "labels_25.json"
    labels.write_text("[]")
    with pytest.raises(OrderingError, match="not committed"):
        require_committed_labels(labels, repo)


def test_guard_rejects_labels_edited_since_their_commit(repo):
    labels = repo / "labels_25.json"
    labels.write_text('{"labels": []}')
    _git(repo, "add", "labels_25.json")
    _git(repo, "commit", "-qm", "labels")
    labels.write_text('{"labels": [{"case_id": "W6-01", "label": true}]}')
    with pytest.raises(OrderingError, match="modified since"):
        require_committed_labels(labels, repo)


def test_guard_accepts_committed_clean_labels_and_returns_the_proof(repo):
    labels = repo / "labels_25.json"
    labels.write_text('{"labels": []}')
    _git(repo, "add", "labels_25.json")
    _git(repo, "commit", "-qm", "labels")
    proof = require_committed_labels(labels, repo)
    assert len(proof["labels_commit"]) == 40
    assert proof["labels_sha256"] == sha256_file(labels)


def test_build_judge_messages_shows_question_chunks_and_answer():
    rec = {
        "question": "What is the default?",
        "retrieved": [{"chunk_id": "v3:client:structural:2", "source_file": "v3/client.md", "text": "2000 ms"}],
        "raw_output": "It is 2000 ms in v3.",
    }
    messages = build_judge_messages("PROMPT", rec)
    user = messages[1]["content"]
    assert "What is the default?" in user
    assert "v3:client:structural:2" in user
    assert "It is 2000 ms in v3." in user


def test_run_judge_records_the_labels_commit_as_ordering_proof(repo):
    labels = repo / "labels_25.json"
    labels.write_text('{"labels": []}')
    _git(repo, "add", "labels_25.json")
    _git(repo, "commit", "-qm", "labels")

    prompt = repo / "judge_v1.txt"
    prompt.write_text("CRITERION: Would a developer act on this?\nVERDICT:\nREASON:\n")

    snapshot = {
        "answers_sha256": "abc123",
        "answers": [
            {"case_id": "W6-01", "question": "q", "retrieved": [], "raw_output": "a"},
            {"case_id": "W6-02", "question": "q", "retrieved": [], "raw_output": "b"},
        ],
    }
    calls = []

    def fake_call(model, messages):
        calls.append(model)
        return "VERDICT: PASS\nREASON: fine"

    result = run_judge(prompt, snapshot, labels, "test-model", call_fn=fake_call)

    assert len(result["verdicts"]) == 2
    assert result["labels_commit"]
    assert result["labels_sha256"] == sha256_file(labels)
    assert result["answers_sha256"] == "abc123"
    assert calls == ["test-model", "test-model"]


def test_run_judge_refuses_before_making_a_single_model_call(repo):
    """The guard must run BEFORE the API calls, or an uncommitted-labels run
    still costs money and still leaves verdicts you have now seen."""
    labels = repo / "labels_25.json"
    labels.write_text("{}")
    prompt = repo / "judge_v1.txt"
    prompt.write_text("CRITERION: x\n")
    calls = []

    def fake_call(model, messages):
        calls.append(model)
        return "VERDICT: PASS\nREASON: fine"

    with pytest.raises(OrderingError):
        run_judge(prompt, {"answers_sha256": "x", "answers": [{"case_id": "W6-01", "question": "q", "retrieved": [], "raw_output": "a"}]}, labels, "m", call_fn=fake_call)
    assert calls == [], "no model call may happen before the ordering guard passes"


def test_the_committed_labels_were_never_edited_after_the_judge_ran():
    """The task's sharpest trap: reaching a higher agreement by relabelling
    the cases you disagreed on moves the ruler, not the thing being measured.
    This makes that mechanically detectable instead of a matter of conscience.
    """
    from pathlib import Path

    from eval.week6.judge import LABELS_PATH, run_path_for

    if not LABELS_PATH.exists():
        pytest.skip("labels not written yet")

    for version in ("v1", "v2"):
        path = run_path_for(version)
        if not path.exists():
            continue
        recorded = json.loads(path.read_text(encoding="utf-8"))["labels_sha256"]
        assert recorded == sha256_file(LABELS_PATH), (
            f"labels_25.json changed since judge_{version} ran"
        )
