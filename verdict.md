# Verdict: KILL

1. Pass rate tied: 90% (9/10) single agent vs 90% (9/10) squad -- no correctness benefit from the extra agents.
2. p50 latency nearly doubled: 12.37s -> 23.81s; p99 more than doubled: 31.46s -> 72.44s.
3. Squad burned 1.3x the tokens (40,010 vs 29,751) at ~1.6x cost/question ($0.00101 vs $0.00062).
4. Single largest cost: orchestrator->code_sample_worker alone = 50% of all squad tokens -- a second full tool-use loop the single agent never pays for.
5. One point in its favor: under an injected HTTP 500 on the deprecation worker, the orchestrator retried once, then degraded gracefully and admitted the gap instead of hallucinating.
6. That one resilience win doesn't offset paying roughly double the latency and 1.6x the cost for an identical pass rate.
7. Sunk-cost check: we spent this whole week building the routing/retry/synthesis logic, which makes it tempting to keep anyway -- but effort spent isn't evidence of value delivered.
8. Decision: KILL. Route this workload back through the single agent.
9. Keep only the retry-then-admit-the-gap pattern as something worth adding directly to the single agent later, without the extra agents.
