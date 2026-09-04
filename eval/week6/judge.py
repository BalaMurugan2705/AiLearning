"""Runs a judge prompt over the frozen snapshot, and refuses to run early.

The rubric scores the ordering, not just the numbers: hand labels must
provably predate the judge run. Timestamps are weak evidence -- anyone can
touch a file. So this module reads git, refuses when the labels file is
uncommitted or dirty, and stamps the labels' commit hash and sha256 into its
output. The resulting run file physically contains a hash that could only
exist if the labels were committed first.
"""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from eval.week6.criterion import JUDGE_V1_PATH, JUDGE_V2_PATH
from eval.week6.snapshot import load_snapshot
from rag.config import GROQ_API_KEY, JUDGE_MODEL

BASE = Path(__file__).resolve().parent
REPO = BASE.parent.parent
LABELS_PATH = BASE / "labels_25.json"
RAW_DIR = REPO / "eval" / "raw"

_VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(PASS|FAIL)\s*$", re.MULTILINE | re.IGNORECASE)
_REASON_RE = re.compile(r"^\s*REASON:\s*(.+)$", re.MULTILINE)

UNPARSED = "UNPARSED"


class OrderingError(Exception):
    """Raised when the blind protocol would be violated."""


def run_path_for(version: str) -> Path:
    return RAW_DIR / f"judge_{version}_run.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_verdict(raw: str) -> tuple[str, str]:
    """Strict parse. Anything that is not the contract is UNPARSED.

    Coercing a rambling reply into a PASS would invent agreement out of a
    formatting failure, which is the one error that would corrupt the headline
    number without leaving a trace.
    """
    match = _VERDICT_RE.search(raw)
    if match is None:
        return (UNPARSED, "")
    reason = _REASON_RE.search(raw)
    return (match.group(1).upper(), reason.group(1).strip() if reason else "")


def require_committed_labels(labels_path: Path, repo: Path) -> dict:
    """Proof that the labels predate this run, or refuse to run."""
    if not labels_path.exists():
        raise OrderingError(f"{labels_path} does not exist -- label before judging.")

    rel = labels_path.resolve().relative_to(repo.resolve()).as_posix()
    # check=False: a repo with zero commits yet (no HEAD) makes `git log`
    # exit non-zero rather than print nothing -- both cases mean "no commit
    # touches this file," i.e. not committed, so both fold into empty commit.
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", rel],
        cwd=repo, capture_output=True, text=True, check=False,
    ).stdout.strip()
    if not commit:
        raise OrderingError(
            f"{rel} is not committed. The blind protocol requires the labels to be "
            "committed BEFORE the judge runs -- an uncommitted file is not evidence "
            "of anything. Commit it on its own, then re-run."
        )

    dirty = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", rel], cwd=repo
    ).returncode
    if dirty != 0:
        raise OrderingError(
            f"{rel} has been modified since commit {commit[:12]}. Labels are frozen "
            "once committed: editing them to match the judge would move the ruler "
            "instead of the thing being measured."
        )

    return {"labels_commit": commit, "labels_sha256": sha256_file(labels_path)}


def _repo_root_for(path: Path) -> Path:
    """The git repository that actually contains `path`, found via git itself.

    Hardcoding the project's own REPO as the universal default would break
    any caller whose labels file lives under a different repository -- e.g. a
    test's own throwaway git repo -- since `git log`/`git diff` must run with
    a cwd inside the repo that tracks the file being checked.
    """
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path.resolve().parent, capture_output=True, text=True, check=True,
    ).stdout.strip()
    return Path(top)


def build_judge_messages(prompt_text: str, answer_rec: dict) -> list[dict]:
    chunks = "\n\n".join(
        f"[chunk: {c.get('chunk_id')} | {c.get('source_file')}]\n{c.get('text', '')}"
        for c in answer_rec["retrieved"]
    ) or "(nothing retrieved)"
    user = (
        f"QUESTION:\n{answer_rec['question']}\n\n"
        f"RETRIEVED DOCUMENTATION:\n{chunks}\n\n"
        f"ANSWER UNDER REVIEW:\n{answer_rec['raw_output']}"
    )
    return [{"role": "system", "content": prompt_text}, {"role": "user", "content": user}]


def _groq_call(model: str, messages: list[dict]) -> str:
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model=model, messages=messages, temperature=0, max_tokens=256
    )
    return completion.choices[0].message.content or ""


def run_judge(
    prompt_path: Path,
    snapshot: dict,
    labels_path: Path,
    model: str,
    call_fn=_groq_call,
    repo: Path | None = None,
) -> dict:
    # The guard runs before the first model call. Checking afterwards would
    # still cost money and would still leave verdicts you have now seen.
    proof = require_committed_labels(labels_path, repo or _repo_root_for(labels_path))
    prompt_text = prompt_path.read_text(encoding="utf-8")

    verdicts = []
    for rec in snapshot["answers"]:
        raw = call_fn(model, build_judge_messages(prompt_text, rec))
        verdict, reason = parse_verdict(raw)
        verdicts.append(
            {"case_id": rec["case_id"], "verdict": verdict, "reason": reason, "raw": raw}
        )

    return {
        "judge_prompt": prompt_path.as_posix(),
        "judge_prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        "judge_model": model,
        "temperature": 0,
        "answers_sha256": snapshot["answers_sha256"],
        "labels_commit": proof["labels_commit"],
        "labels_sha256": proof["labels_sha256"],
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdicts": verdicts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=("v1", "v2"), required=True)
    args = parser.parse_args()

    prompt_path = JUDGE_V1_PATH if args.version == "v1" else JUDGE_V2_PATH
    result = run_judge(prompt_path, load_snapshot(), LABELS_PATH, JUDGE_MODEL)

    out = run_path_for(args.version)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    counts = {}
    for v in result["verdicts"]:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    print(f"wrote {out}")
    print(f"verdicts: {counts}")
    print(f"labels_commit: {result['labels_commit']}  (ordering proof)")


if __name__ == "__main__":
    main()
