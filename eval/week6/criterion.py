"""Single source of truth for the judge's one criterion.

label.py shows the labeler this exact text and judge.py sends this exact text
to the model. Duplicating the sentence in two places would let the human and
the judge drift onto slightly different questions, and agreement between
answers to different questions is not agreement.
"""
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
WEEK6_RESULTS = REPO / "results" / "week6"

JUDGE_V0_PATH = WEEK6_RESULTS / "judge_v0.txt"
JUDGE_V1_PATH = WEEK6_RESULTS / "judge_v1.txt"
JUDGE_V2_PATH = WEEK6_RESULTS / "judge_v2.txt"

CRITERION_MARKER = "CRITERION:"


def read_criterion(path: Path) -> str:
    """The text after the single CRITERION: marker in a judge prompt."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(CRITERION_MARKER):
            return line.split(CRITERION_MARKER, 1)[1].strip()
    raise ValueError(f"{path} has no {CRITERION_MARKER} line")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
