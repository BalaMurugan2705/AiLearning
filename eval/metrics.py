"""Hit scoring for the chunking comparison.

Two metrics over the same retrieval results:

Metric A — pre-registered before any index was built. A hit is a chunk in the
top k that comes from the expected page and whose text contains the known
answer span. The page guard stops a coincidental match on another page from
counting.

Metric B — added after metric A scored 8/8 for both strategies and therefore
failed to distinguish them. A supported hit additionally requires every
support span to appear in that same chunk. For a parameter-table question the
support spans are the parameter name and the table's header row, so metric B
is a direct test of requirement 3's wording: is the parameter row still
attached to its header row? Questions with no support spans (prose answers)
score identically under both metrics by construction.

Metric A is reported alongside B rather than replaced by it. Dropping the
pre-registered metric because it gave an inconvenient answer would be the
failure the pre-registration exists to prevent.
"""


def _qualifies(result: dict, question: dict, require_support: bool) -> bool:
    if result["metadata"].get("source_file") != question["page"]:
        return False

    text = result["text"]
    if question["answer_span"] not in text:
        return False

    if not require_support:
        return True

    return all(span in text for span in question.get("support_spans", []))


def _first_rank(results: list[dict], question: dict, require_support: bool) -> int | None:
    for result in results:
        if _qualifies(result, question, require_support):
            return result["rank"] + 1
    return None


def score_question(results: list[dict], question: dict) -> dict:
    """Score one question under both metrics. Ranks are 1-based."""
    hit_rank = _first_rank(results, question, require_support=False)
    supported_rank = _first_rank(results, question, require_support=True)
    return {
        "hit": hit_rank is not None,
        "hit_rank": hit_rank,
        "supported_hit": supported_rank is not None,
        "supported_hit_rank": supported_rank,
    }
