Here is the structured, refined, and easy-to-understand breakdown for the **Week 10 Engineering Challenge**, formatted identically to Week 8 and Week 9 so you can share it directly with your team.

---

# Week 10 Engineering Challenge: Multi-Agent Squad vs. Single Agent Race

### **Overview & Objective**

In Week 10, the core focus shifts to **Multi-Agent Systems & Agent-to-Agent (A2A) Protocols**.

The main goal this week is to run an honest, data-backed experiment: build a **Manager-Plus-Two-Specialists Team** (an Orchestrator delegating to a `version/deprecation worker` and a `code-sample worker`) and race it head-to-head against your existing **Single Agent**. Rather than blindly adopting multi-agent architecture because it's popular, you will prove using hard performance numbers whether a team of agents is actually better or if it just inflates token bills and latency.

---

### **Key Technical Deliverables**

#### **1. The Head-to-Head Race (`race_table.md`)**

* Run both arms (Single Agent vs. Orchestrator Squad) through the **exact same 10 Week-6 evaluation cases** using the same evaluator model.
* **Collect & Report 4 Core Telemetry Metrics for BOTH Arms:**
1. **Pass Rate:** Correctness and accuracy percentage.
2. **p50 & p99 Latency:** Execution speed and worst-case delay.
3. **Total Tokens:** Total input and output token consumption.
4. **Cost Per Question:** Dollar amount spent per query.


#### **2. Context Re-Send Analysis (`handoffs.log`)**

* Log every agent-to-agent delegation hop along with its exact token cost.
* **Calculate the Token Multiplier:**

$$\text{Context Re-Send Multiplier} = \frac{\text{Multi-Agent Total Tokens}}{\text{Single Agent Total Tokens}} \quad \text{(rounded to 1 decimal place)}$$


* **Identify the Largest Bottleneck:** Attribute the single largest token share to a specific hand-off step from your log (e.g., `"orchestrator -> code-sample worker resend: 41% of total tokens"`).

#### **3. Failure Injection & Resilience Check (`failure_case.md`)**

* Inject a deliberate system failure: force the `version/deprecation worker` to return an **HTTP 500 error** on one evaluation test case.
* Document what the orchestrator *actually* did in response:
* Did it **retry** the request?
* Did it **degrade gracefully** into a partial answer?
* Did it **hallucinate/lie** (e.g., shipping a code sample without verifying the version)?



#### **4. Architecture Verdict (`verdict.md`)**

* Write a final **KEEP** or **KILL** decision on the multi-agent system in **10 lines or fewer**.
* Base your decision on at least **two concrete telemetry numbers** from your race.
* **Call Out Sunk-Cost Bias:** Explicitly address the emotional temptation to keep complex multi-agent code simply because you spent time building it.

---

### **Evaluation Rubric & Scoring Breakdown (100 Points)**

| Criterion | Points | Focus Area |
| --- | --- | --- |
| **Comparative Telemetry** | **30** | All 4 metrics (Pass rate, p50/p99 latency, tokens, cost) reported for **both** arms on the identical 10 Week-6 test cases. |
| **Context Re-Send Multiplier** | **25** | Calculated multiplier ($\frac{\text{Multi}}{\text{Single}}$) with the single largest token bottleneck attributed. |
| **Failure Mode Injection** | **20** | Injected HTTP 500 error on a worker; orchestrator behavior (retry, degrade, lie) recorded honestly. |
| **Data-Backed Verdict** | **15** | Clear KEEP or KILL decision citing $\ge 2$ metrics while acknowledging sunk-cost bias out loud. |
| **Hand-Off Log Trace** | **10** | Detailed `handoffs.log` capturing per-hand-off token counts for every inter-agent call. |

---

### **Submission Checklist**

* [ ] `race_table.md` — 4 metrics $\times$ 2 arms across the 10 Week-6 test cases.
* [ ] `handoffs.log` — Log capturing every inter-agent delegation and its token count.
* [ ] **Multiplier Calculation** — $\frac{\text{Multi-Agent}}{\text{Single Agent}}$ token ratio with the dominant hand-off step named.
* [ ] `failure_case.md` — The injected HTTP 500 worker failure and the orchestrator's real behavior.
* [ ] `verdict.md` — Max 10 lines, citing $\ge 2$ metrics, with sunk-cost bias explicitly named.

---

### **Bonus Challenge: AgentCard & A2A Lifecycle Mapping**

* **Publish AgentCard:** Define the capability schema, input/output interfaces, and authentication required for your orchestrator.
* **Map onto A2A Task State Machine:** Map the 500 error case onto the A2A task lifecycle (e.g., whether it terminates as `FAILED` or transitions to `PAUSED: input-required` to ask the user for their target SDK version).
* **Protocol Value:** State in 2 lines what using a formal A2A protocol gives you over standard REST calls between workers.
