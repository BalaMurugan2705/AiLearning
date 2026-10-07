# Race Table: Single Agent vs. Orchestrator Squad

10 cases from `eval/week8/cases.json` (used in place of the task doc's "Week-6 cases" -- see `task/W10-progress-log.md` for why), same model (openai/gpt-oss-120b) for both arms, same deterministic grader (`eval/week7/run_race.py::grade_entry`).

| Metric | Single Agent | Orchestrator Squad |
| --- | --- | --- |
| Pass rate | 90% (9/10) | 90% (9/10) |
| p50 latency (s) | 12.37 | 23.81 |
| p99 latency (s) | 31.46 | 72.44 |
| Total tokens | 29751 | 40010 |
| Cost per question (USD) | $0.00062 | $0.00101 |

**Context Re-Send Multiplier:** 1.3x (40010 squad tokens / 29751 single-agent tokens)

**Largest hand-off bottleneck:** `orchestrator->code_sample_worker` -- 50% of all squad tokens across the 10 cases.
