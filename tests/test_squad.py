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


def test_decide_route_does_not_falsely_match_substring_names():
    specialists = [FakeNamed("search", "s"), FakeNamed("code_search", "c")]
    client = FakeClient(["code_search"])
    matched, normalized, tokens, cost = _decide_route("q", specialists, client)
    assert matched == {"code_search"}


def test_run_specialist_with_retry_succeeds_first_try():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"))
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, backoff_seconds=0,
    )
    assert result.answer == "ok"
    assert error is None
    assert attempts == 1


def test_run_specialist_with_retry_succeeds_on_retry():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"), fail_times=1)
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, backoff_seconds=0,
    )
    assert result.answer == "ok"
    assert attempts == 2


def test_run_specialist_with_retry_gives_up_after_max_attempts():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"), fail_times=5)
    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, backoff_seconds=0,
    )
    assert result is None
    assert attempts == 2
    assert "worker unavailable" in error


def test_run_specialist_with_retry_fault_hook_can_inject_failure():
    specialist = FakeSpecialist("custom_worker", result=_specialist_result("ok"))

    def hook(sp):
        if sp.name == "custom_worker":
            raise RuntimeError("HTTP 500: custom_worker service unavailable")

    result, error, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, fault_hook=hook, backoff_seconds=0,
    )
    assert result is None
    assert "custom_worker service unavailable" in error


def test_run_specialist_with_retry_does_not_retry_non_retryable_errors():
    from agent.errors import McpConsentRequired

    class Consent(FakeSpecialist):
        def run(self, task, client=None):
            self.call_count += 1
            raise McpConsentRequired("consent required")

    specialist = Consent("worker")
    result, error, attempts = _run_specialist_with_retry(specialist, "q", client=None, backoff_seconds=0)
    assert result is None and attempts == 1 and "consent" in error


def test_run_specialist_with_retry_rejects_budget_terminated_result():
    bad = SimpleNamespace(answer=None, terminated_by_budget=True, budget_reason="max_iterations", tool_calls=[],
                          total_tokens=1, total_cost_usd=0)
    specialist = FakeSpecialist("worker", result=bad)
    result, error, attempts = _run_specialist_with_retry(specialist, "q", client=None, backoff_seconds=0)
    assert result is None
    assert "budget" in error
    assert attempts == 2


def test_run_specialist_with_retry_rejects_answer_without_successful_tool_evidence():
    fabricated = SimpleNamespace(
        answer="no deprecations", terminated_by_budget=False, total_tokens=1, total_cost_usd=0,
        tool_calls=[{"tool": "t", "arguments": {}, "status": "error", "result_excerpt": "invalid_arguments"}],
    )
    specialist = FakeSpecialist("worker", result=fabricated)
    result, error, _ = _run_specialist_with_retry(specialist, "q", client=None, backoff_seconds=0)
    assert result is None
    assert "no successful tool evidence" in error


def test_run_specialist_with_retry_sleeps_between_attempts():
    specialist = FakeSpecialist("worker", result=_specialist_result("ok"), fail_times=1)
    sleeps = []
    result, _, attempts = _run_specialist_with_retry(
        specialist, "q", client=None, backoff_seconds=0.5, sleep=sleeps.append,
    )
    assert attempts == 2 and sleeps == [0.5]


def test_run_squad_treats_budget_terminated_specialist_as_failed(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")
    monkeypatch.setattr("agent.squad.time.sleep", lambda s: None)
    bad = SimpleNamespace(answer=None, terminated_by_budget=True, budget_reason="max_iterations",
                          tool_calls=[], total_tokens=1, total_cost_usd=0)
    dep = FakeSpecialist("deprecation_worker", result=bad)
    client = FakeClient(["deprecation_worker"])
    result = run_squad("q", [dep], client=client)
    assert result.status == "paused_input_required"
    assert any(h["status"] == "error" for h in result.handoffs)


def test_run_squad_returns_and_forwards_tool_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")
    good = SimpleNamespace(
        answer="dep answer", terminated_by_budget=False, total_tokens=1, total_cost_usd=0,
        tool_calls=[{"tool": "check_x", "arguments": {"a": 1}, "status": "ok", "result_excerpt": "RAW-FACT"}],
    )
    dep = FakeSpecialist("deprecation_worker", result=good)
    client = FakeClient(["deprecation_worker", "final"])
    result = run_squad("q", [dep], client=client)
    assert result.evidence["deprecation_worker"][0]["tool"] == "check_x"
    assert "RAW-FACT" in client.sent_messages[-1][1]["content"]


def test_run_squad_optional_llm_verification_flags_unsupported_answer(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")
    dep = FakeSpecialist("deprecation_worker", result=_specialist_result("dep answer"))
    client = FakeClient(["deprecation_worker", "final", "UNSUPPORTED: claims a field not in evidence"])
    result = run_squad("q", [dep], client=client, verify_with_llm=True)
    assert result.verification["supported"] is False
    assert result.answer.startswith("[Unverified:")


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


from agent.squad import order_by_dependencies, parse_plan


class _Recorder(FakeSpecialist):
    def __init__(self, name, answer):
        super().__init__(name, result=_specialist_result(answer))
        self.tasks = []

    def run(self, task, client=None):
        self.tasks.append(task)
        return super().run(task, client=client)


def test_parse_plan_reads_subtasks_and_dependencies():
    specialists = [FakeNamed("a", ""), FakeNamed("b", "")]
    plan = parse_plan("a: find the spec\nb (after a): write a snippet from it", specialists)
    assert plan == {
        "a": {"task": "find the spec", "after": []},
        "b": {"task": "write a snippet from it", "after": ["a"]},
    }
    assert parse_plan("a, b", specialists) == {}


def test_order_by_dependencies_respects_order_and_survives_cycles():
    plan = {"a": {"task": "", "after": ["b"]}, "b": {"task": "", "after": []}}
    assert order_by_dependencies(["a", "b"], plan) == ["b", "a"]
    cyc = {"a": {"task": "", "after": ["b"]}, "b": {"task": "", "after": ["a"]}}
    assert sorted(order_by_dependencies(["a", "b"], cyc)) == ["a", "b"]
    assert order_by_dependencies(["a"], plan) == ["a"]  # dependency not routed -> dropped


def test_run_squad_runs_dependent_specialist_after_and_passes_its_result(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")
    first = _Recorder("code_sample_worker", "SPEC-FACT")
    second = _Recorder("deprecation_worker", "dep answer")
    # config order is [deprecation_worker, code_sample_worker]; the plan reverses it
    route = "code_sample_worker: find the spec\ndeprecation_worker (after code_sample_worker): check it"
    client = FakeClient([route, "final"])
    result = run_squad("orig question", [second, first], client=client)
    hops = [h["hop"] for h in result.handoffs if h["hop"].startswith("orchestrator->") and "routing" not in h["hop"]]
    assert hops[:2] == ["orchestrator->code_sample_worker", "orchestrator->deprecation_worker"]
    assert "find the spec" in first.tasks[0] and "orig question" in first.tasks[0]
    assert "SPEC-FACT" in second.tasks[0] and "check it" in second.tasks[0]


def test_run_squad_tells_dependent_specialist_when_its_dependency_failed(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")
    monkeypatch.setattr("agent.squad.time.sleep", lambda s: None)
    first = FakeSpecialist("a_worker", result=None, fail_times=99)
    second = _Recorder("b_worker", "b answer")
    client = FakeClient(["a_worker: x\nb_worker (after a_worker): y", "final"])
    result = run_squad("q", [first, second], client=client)
    assert result.status == "completed"
    assert "a_worker FAILED" in second.tasks[0]


from agent.verification import evidence_footer, plan_warnings, ungrounded_claims


def _ev(result):
    return {"w": [{"tool": "t", "arguments": {"endpoint": "create_issue"}, "status": "ok",
                   "result_excerpt": result[:10], "result": result}]}


def test_ungrounded_claims_flags_invented_specifics_only():
    evidence = _ev('{"params": ["assignees"], "api_version": "2025-06-01"}')
    answer = "In 2025-06-01 use `assignees`, not `assignee`. Also 2031-01-01 changed it.\n```\nclient.foo_bar()\n```"
    assert set(ungrounded_claims(answer, "q", evidence)) == {"2031-01-01", "assignee"}
    assert "foo_bar" not in " ".join(ungrounded_claims(answer, "q", evidence))  # code blocks skipped


def test_ungrounded_claims_allows_facts_from_the_question():
    assert ungrounded_claims("About 2025-06-01.", "what changed in 2025-06-01?", _ev("x")) == []


def test_evidence_footer_lists_only_successful_calls():
    ev = {"w": [{"tool": "ok_tool", "arguments": {"a": 1}, "status": "ok", "result_excerpt": ""},
                {"tool": "bad_tool", "arguments": {}, "status": "error", "result_excerpt": ""}]}
    footer = evidence_footer(ev)
    assert "ok_tool(a=1)" in footer and "bad_tool" not in footer
    assert evidence_footer({}) == ""


def test_plan_warnings_report_dropped_dependencies_and_cycles():
    plan = {"a": {"task": "", "after": ["b"]}, "b": {"task": "", "after": ["a"]}, "c": {"task": "", "after": ["z"]}}
    warnings = plan_warnings(plan, ["a", "b", "c"])
    assert any("cycle" in w for w in warnings)
    assert any("c depends on z" in w for w in warnings)


def test_run_squad_flags_ungrounded_final_answer_and_appends_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.squad.HANDOFFS_LOG_PATH", tmp_path / "handoffs.log")
    good = SimpleNamespace(
        answer="dep answer", terminated_by_budget=False, total_tokens=1, total_cost_usd=0,
        tool_calls=[{"tool": "check_x", "arguments": {"a": 1}, "status": "ok",
                     "result_excerpt": "fact", "result": "fact 2025-06-01"}],
    )
    dep = FakeSpecialist("deprecation_worker", result=good)
    client = FakeClient(["deprecation_worker", "Changed in 2031-01-01 and 2025-06-01."])
    result = run_squad("q", [dep], client=client)
    assert result.verification["ungrounded_claims"] == ["2031-01-01"]
    assert result.answer.startswith("[Unverified:")
    assert "Evidence (tool calls):" in result.answer and "check_x(a=1)" in result.answer
    plain = run_squad("q", [FakeSpecialist("deprecation_worker", result=good)],
                      client=FakeClient(["deprecation_worker", "ok 2025-06-01"]), evidence_in_answer=False)
    assert plain.answer == "ok 2025-06-01" and plain.verification["supported"] is True
