
from dataclasses import dataclass, field


@dataclass
class OrchestratorResult:
    """The result returned by the multi-agent orchestrator."""

    answer: str
    specialist_results: list[dict] = field(default_factory=list)


def run_orchestrator(
    question: str,
    specialists: list,
) -> OrchestratorResult:
    """
    Delegate a user question to specialist agents sequentially.

    Each specialist must implement a run(task) method and return
    an object containing an answer attribute.
    """

    specialist_results = []

    for specialist in specialists:
        result = specialist.run(question)

        specialist_results.append({
            "agent": specialist.name,
            "task": question,
            "answer": result.answer,
        })

    # First version: combine the specialists' answers directly.
    # We will add LLM-based synthesis in a later step.
    answer = "\n\n".join(
        f"{item['agent']}: {item['answer']}"
        for item in specialist_results
    )

    return OrchestratorResult(
        answer=answer,
        specialist_results=specialist_results,
    )