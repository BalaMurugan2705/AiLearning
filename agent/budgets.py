import time
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class Budget:
    max_iterations: int
    max_tokens: int
    max_cost_usd: float
    max_wall_seconds: float


@dataclass
class BudgetTracker:
    """Tracks one agent run's spend against a Budget.

    Call start_iteration() at the top of every loop lap, before the next
    model call. Call record_usage() right after each model call returns,
    before deciding whether to loop again.
    """

    budget: Budget
    iterations: int = field(default=0, init=False)
    total_tokens: int = field(default=0, init=False)
    total_cost_usd: float = field(default=0.0, init=False)
    _start: float = field(default_factory=time.monotonic, init=False)

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def start_iteration(self) -> None:
        self.iterations += 1
        if self.iterations > self.budget.max_iterations:
            raise BudgetExceeded(
                f"max_iterations exceeded: {self.iterations} > {self.budget.max_iterations}"
            )
        elapsed = self.elapsed()
        if elapsed > self.budget.max_wall_seconds:
            raise BudgetExceeded(
                f"max_wall_seconds exceeded: {elapsed:.2f}s > {self.budget.max_wall_seconds}s"
            )

    def record_usage(
        self, prompt_tokens: int, completion_tokens: int, price_in: float, price_out: float
    ) -> None:
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost_usd += (
            prompt_tokens * price_in + completion_tokens * price_out
        ) / 1_000_000
        if self.total_tokens > self.budget.max_tokens:
            raise BudgetExceeded(
                f"max_tokens exceeded: {self.total_tokens} > {self.budget.max_tokens}"
            )
        if self.total_cost_usd > self.budget.max_cost_usd:
            raise BudgetExceeded(
                f"max_cost_usd exceeded: ${self.total_cost_usd:.4f} > ${self.budget.max_cost_usd}"
            )
