<!-- Soft Suave · The AI Engineering League -->
# Week 7 Practical — Task Set E

## Race the docs agent against a fixed workflow

| | |
|---|---|
| Domain | Developer documentation |
| Week | 7 — Agent Loops — and When Not to Use Them |
| Module | M4 — Agents |
| Sat on | Week 8 · Monday |
| Marks | 100 |

> **This is an extension of the app you already built in Week 7.** It is not a build from scratch, and it tests only this week's concepts. Bring your numbers written down.


---

## 1. Problem statement

Your hand-built agent answers migration questions: find the docs page, read the OpenAPI spec, check the changelog for deprecations, write the v3 code sample. A tech lead asks the question you should have asked first — does this need to be an agent at all, or would three hard-coded steps be faster, cheaper and more debuggable? Settle it with four numbers rather than an opinion.


---

## 2. Requirements

1. Add a third tool to the existing loop (get_changelog or check_deprecation) whose description names exactly one job, uses an enum for the api_version parameter, and does not overlap the two existing tool descriptions.
2. Re-implement the identical task as a fixed workflow — hard-coded steps, same tools, same model, same output contract. No loop.
3. Race agent vs workflow over the same 10 questions (including at least 3 where step 3 depends on what step 2 found, e.g. the endpoint is deprecated in v3 so the replacement must be looked up) and report four numbers for each: pass rate, p50 latency, total tokens, cost per question.
4. Enforce all four budgets in the loop — max iterations, max tokens, max cost, wall-clock — and include the log of one run that hits a budget and terminates cleanly instead of spinning.
5. Write the verdict applying the decision rule (does the path vary by input?), naming the specific question class that forces an agent — or stating honestly that none of the 10 does.


---

## 3. Expected output

race.csv or a table with 8 numbers (4 per system), the workflow implementation, the budget-termination log, the third tool's description diff, and a verdict paragraph of under 150 words.


---

## 4. Evaluation rubric

| Criterion | Points |
|---|---|
| Four numbers for both systems over the same 10 inputs — pass rate, p50 latency, tokens, cost/task — reported as one comparable table | 30 |
| The workflow genuinely does the same task: same inputs, same output contract, same tools, no loop hiding inside it | 20 |
| All four budgets enforced in code plus a log showing one clean budget termination | 20 |
| Verdict applies the decision rule to a named input class and is consistent with your own numbers — a verdict contradicting the table scores 0 here | 20 |
| Third tool: one job, typed/enum parameters, no description overlap with existing tools | 10 |
| **Total** | **100** |

*Zero points for polish, UI, or "it works". This mirrors the House rubric: failure-finding and a number that moved are what score.*


---

## 5. Bonus challenge

Add a sliding window plus summarisation to the agent so it survives a 30-turn migration thread, and persist one fact (the caller's pinned API version) across a full process restart. Re-run the race on 3 long threads and name one detail summarisation destroyed and the question it broke.


---

## 6. Submission checklist

- [ ] Agent and workflow both runnable by one command each
- [ ] race.csv / table with all 8 numbers over the same 10 docs questions
- [ ] Log excerpt of the budget-triggered termination, showing which budget fired
- [ ] Diff of the third tool's description and parameter enums
- [ ] Verdict paragraph naming the question class that does or does not need an agent


---

## 7. Common mistakes

- **Racing on 10 single-page lookup questions the agent already passes — the race is decided by the input mix, and without the deprecated-endpoint and cross-version cases the workflow wins by construction.**
- **Declaring the agent the winner on adaptability while your own table shows the workflow ahead on all four numbers — that is fashion overruling the rule you were taught.**
- **Counting only the final call's tokens; the loop re-sends the whole message list every lap, so per-lap tokens must be summed or the agent's cost is understated by multiples.**
- **Defining MAX_ITERS, MAX_TOKENS, MAX_COST as constants and never checking three of them in the loop — an unenforced budget is a comment with ambition.**
- **Fixing tool thrash by switching model or bolting 'use the correct tool' onto the system prompt instead of sharpening the overlapping search_docs / get_openapi_spec descriptions — the description bug stays, and it will resurface on the next tool you add.**


---

*Set E of 6. Sets A–F are equivalent in difficulty and objectives; only the domain differs.*
