from dataclasses import dataclass
from types import SimpleNamespace

from agent.squad import (
    build_routing_prompt,
    _decide_route,
    _run_specialist_with_retry,
    run_squad,
)


@dataclass
class FakeNamed:
    name: str
    description: str


class FakeSpecialist:
    def __init__(self, name, result=None, fail_times=0):
        self.name = name
        self.description = f"{name} description"
        self._result = result
        self._fail_times = fail_times
        self.call_count = 0

    def run(self, task, client=None):
        self.call_count += 1
        if self.call_count <= self._fail_times:
            raise RuntimeError(f"{self.name} unavailable")
        return self._result


class FakeClient:
    """Stands in for the Groq client. Each call to chat.completions.create
    pops the next canned response, in call order (routing first, then
    synthesis if it happens)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.sent_messages = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages):
        self.sent_messages.append(messages)
        content = self._responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


def _specialist_result(answer):
    return SimpleNamespace(answer=answer, total_tokens=20, total_cost_usd=0.002)


def test_build_routing_prompt_lists_every_specialist():
    specialists = [FakeNamed("a", "desc A"), FakeNamed("b", "desc B")]
    prompt = build_routing_prompt(specialists)
    assert "a" in prompt and "desc A" in prompt
    assert "b" in prompt and "desc B" in prompt


def test_decide_route_matches_named_specialist():
    specialists = [FakeNamed("deprecation_worker", "d"), FakeNamed("code_sample_worker", "c")]
    client = FakeClient(["deprecation_worker"])
    matched, normalized, tokens, cost = _decide_route("q", specialists, client)
    assert matched == {"deprecation_worker"}


def test_decide_route_falls_back_to_all_when_unparseable():
    specialists = [FakeNamed("deprecation_worker", "d"), FakeNamed("code_sample_worker", "c")]
    client = FakeClient(["I'm not sure"])
    matched, normalized, tokens, cost = _decide_route("q", specialists, client)
    assert matched == {"deprecation_worker", "code_sample_worker"}


def test_decide_route_falls_back_to_all_on_empty_response():
    specialists = [FakeNamed("deprecation_worker", "d"), FakeNamed("code_sample_worker", "c")]
    client = FakeClient([""])
    matched, normalized, tokens, cost = _decide_route("q", specialists, client)
    assert matched == {"deprecation_worker", "code_sample_worker"}


def test_run_specialist_with_retry_succeeds_first_try():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"))
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure=None,
    )
    assert result.answer == "ok"
    assert error is None
    assert attempts == 1


def test_run_specialist_with_retry_succeeds_on_retry():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"), fail_times=1)
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure=None,
    )
    assert result.answer == "ok"
    assert attempts == 2


def test_run_specialist_with_retry_gives_up_after_max_attempts():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"), fail_times=5)
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure=None,
    )
    assert result is None
    assert attempts == 2
    assert "worker unavailable" in error


def test_run_specialist_with_retry_force_failure_matches_by_name():
    specialist = FakeSpecialist("custom_worker", result=_specialist_result("ok"))
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure="custom_worker",
    )
    assert result is None
    assert "custom_worker service unavailable" in error


def test_run_specialist_with_retry_force_failure_name_mismatch_does_not_trigger():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"))
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, force_failure="some_other_worker",
    )
    assert result.answer == "ok"
    assert error is None
    assert attempts == 1


def test_run_squad_routes_to_one_specialist_and_skips_the_other(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    dep = FakeSpecialist("deprecation_worker", result=_specialist_result("dep answer"))
    code = FakeSpecialist("code_sample_worker", result=_specialist_result("code answer"))
    client = FakeClient(["deprecation_worker", "final synthesized answer"])

    result = run_squad("q", [dep, code], client=client)

    assert result.status == "completed"
    assert code.call_count == 0
    assert dep.call_count == 1
    assert result.answer == "final synthesized answer"


def test_run_squad_synthesizes_from_partial_failure(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    dep = FakeSpecialist("deprecation_worker", result=None, fail_times=99)
    code = FakeSpecialist("code_sample_worker", result=_specialist_result("code answer"))
    client = FakeClient(["deprecation_worker, code_sample_worker", "final synthesized answer"])

    result = run_squad("q", [dep, code], client=client)

    assert result.status == "completed"
    synthesis_user_content = client.sent_messages[-1][1]["content"]
    assert "deprecation_worker" in synthesis_user_content
    assert "error" in synthesis_user_content.lower()


def test_run_squad_synthesizes_from_partial_failure_when_second_specialist_fails(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    dep = FakeSpecialist("deprecation_worker", result=_specialist_result("dep answer"))
    code = FakeSpecialist("code_sample_worker", result=None, fail_times=99)
    client = FakeClient(["deprecation_worker, code_sample_worker", "final synthesized answer"])

    result = run_squad("q", [dep, code], client=client)

    assert result.status == "completed"
    synthesis_user_content = client.sent_messages[-1][1]["content"]
    assert "code_sample_worker" in synthesis_user_content
    assert "error" in synthesis_user_content.lower()


def test_run_squad_pauses_when_all_routed_specialists_fail(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    dep = FakeSpecialist("deprecation_worker", result=None, fail_times=99)
    code = FakeSpecialist("code_sample_worker", result=None, fail_times=99)
    client = FakeClient(["deprecation_worker, code_sample_worker"])

    result = run_squad("q", [dep, code], client=client)

    assert result.status == "paused_input_required"
    assert len(client.sent_messages) == 1  # only the routing call -- synthesis never invoked


def test_run_squad_works_with_a_single_configured_specialist(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")

    only = FakeSpecialist("solo_worker", result=_specialist_result("solo answer"))
    client = FakeClient(["solo_worker", "final synthesized answer"])

    result = run_squad("q", [only], client=client)

    assert result.status == "completed"
    assert only.call_count == 1
    assert result.answer == "final synthesized answer"
