# Week 10 Summary: How the Specialist Squad Works

## The big picture

You ask a question. A small "team" of AI helpers answers it. The helpers don't guess. They look things up with tools, and the answer is checked before you see it.

Think of it like an office:
- **Manager** = `run_squad` in `agent/squad.py`
- **Workers** = "specialists" listed in `specialists.json`
- **Tools** = small servers the workers call (MCP servers)

## Step by step

**1. Setup (before any question)**
- `specialists.json` lists two workers:
  - `deprecation_worker` handles exact parameters and deprecated things.
  - `code_sample_worker` handles docs, limits, and gives code snippets.
- Each worker connects to its own tool server and finds out which tools it has.

**2. The manager decides who to ask (routing)**
- The manager asks the AI: "Which worker(s) do we need for this question?"
- It can also give each worker a small task, and say "B runs after A".
- If the AI's answer is unclear, the manager asks **everyone**. That is safer than asking nobody.

**3. Each chosen worker does its job**
Each worker runs a loop, in `agent/loop.py`:
- Think, then call a tool, then read the result.
- Repeat until it has enough, then write an answer.
- There is a budget (tokens, cost, time). If the worker goes over, it is stopped.
- Workers not chosen are logged as "skipped".

**4. Check and retry**
After each worker finishes, `agent/verification.py` checks it. The answer is rejected if:
- the budget cut it off,
- it is empty, or
- no tool call actually succeeded (it may have made things up).

A rejected worker gets one more try. Policy and permission errors are not retried, because retrying can't fix them.

**5. If everyone failed**
The manager stops and asks the user: "Should I wait and retry, or continue with what we have?"

**6. Combine the answers (synthesis)**
If at least one worker succeeded, the manager asks the AI to merge all answers into one. Failed or skipped parts must be called "unavailable", never invented.

**7. Fact-check the final answer**
- **Automatic check:** dates, `code names`, and URL paths in the answer must appear in the question or in a tool result. If not, the answer gets an `[Unverified: ...]` warning.
- **Optional AI fact-checker:** a second AI judges whether the evidence supports the answer.
- Finally, a list of the tool evidence is added to the end.

**8. Logging**
Every step is saved to `handoffs.log`, so you can see who did what and how many tokens it cost.

## One-line summary

**Question → manager picks workers → workers use tools → each worker is checked, with one retry → answers merged → fact-checked → final answer with evidence.**
