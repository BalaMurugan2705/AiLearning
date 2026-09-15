import time

import pytest

from agent.budgets import Budget, BudgetExceeded, BudgetTracker


def _budget(**overrides):
    defaults = dict(max_iterations=5, max_tokens=10_000, max_cost_usd=1.0, max_wall_seconds=60.0)
    defaults.update(overrides)
    return Budget(**defaults)


def test_start_iteration_within_budget_does_not_raise():
    tracker = BudgetTracker(budget=_budget())
    tracker.start_iteration()
    assert tracker.iterations == 1


def test_max_iterations_trips():
    tracker = BudgetTracker(budget=_budget(max_iterations=1))
    tracker.start_iteration()
    with pytest.raises(BudgetExceeded, match="max_iterations"):
        tracker.start_iteration()


def test_max_wall_seconds_trips():
    tracker = BudgetTracker(budget=_budget(max_wall_seconds=0.01))
    time.sleep(0.02)
    with pytest.raises(BudgetExceeded, match="max_wall_seconds"):
        tracker.start_iteration()


def test_max_tokens_trips():
    tracker = BudgetTracker(budget=_budget(max_tokens=100))
    with pytest.raises(BudgetExceeded, match="max_tokens"):
        tracker.record_usage(prompt_tokens=80, completion_tokens=30, price_in=0.0, price_out=0.0)


def test_max_cost_trips():
    # max_tokens set high on purpose: this test isolates the cost budget,
    # so 1,000,000 tokens must not trip max_tokens first.
    tracker = BudgetTracker(budget=_budget(max_cost_usd=0.0001, max_tokens=10_000_000))
    with pytest.raises(BudgetExceeded, match="max_cost_usd"):
        tracker.record_usage(prompt_tokens=1_000_000, completion_tokens=0, price_in=1.0, price_out=1.0)


def test_usage_within_budget_accumulates_without_raising():
    tracker = BudgetTracker(budget=_budget())
    tracker.record_usage(prompt_tokens=50, completion_tokens=50, price_in=0.15, price_out=0.60)
    assert tracker.total_tokens == 100
    assert tracker.total_cost_usd > 0
