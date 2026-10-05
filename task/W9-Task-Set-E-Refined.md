Here is the structured, redefined outline for the **Week 9 Engineering Challenge** ready to share with your engineering team.

---

# Week 9 Engineering Challenge: MCP Integration & Zero-Code Tool Discovery

### **Overview & Objective**

In Week 9, the core focus shifts to **Model Context Protocol (MCP)**—the industry standard for connecting AI agents to tools, data sources, and servers dynamically.

Up until now, integrating a new tool required writing code to import SDKs, define functions, or register parameter schemas. With MCP, tool discovery happens dynamically at runtime via protocol primitives (`initialize`, `tools/list`, `tools/call`). Developers are tasked with attaching a second MCP server (a third-party **Package Registry Server**) to an existing documentation agent **purely through configuration**, proving that tool discovery is truly dynamic while auditing protocol mechanics and supply-chain risks.

---

### **Key Technical Deliverables**

#### **1. Zero-Code Multi-Server Expansion**

* Update your agent's MCP configuration file to register the `package-registry` server alongside your existing `docs-search` server.
* Execute a test query that provably invokes a tool from the new package registry server.
* **Verification Artifact (`agent_diff.txt`):** Submit a `git diff` on your agent module proving **0 lines of code changed** between running single-server and multi-server setups.

#### **2. Protocol Wire & Execution Analysis (`wire.json`)**

* Capture the raw JSON-RPC message exchange across three distinct phases: `initialize`, `tools/list`, and `tools/call`.
* Annotate every top-level protocol field by hand.
* Include a explicit **1-line statement** distinguishing where local JSON-RPC execution occurs versus where the LLM model call takes place (enforcing the architectural boundary that MCP servers expose capabilities, while the host/client runs the model).

#### **3. Dynamic Discovery Telemetry**

* Derive tool counts and names directly from live `tools/list` protocol execution—not from manual developer notes.
* Report the exact discovery change: **$N$ tools before $\rightarrow$ $M$ tools after**.

#### **4. Prompt-Driven Tool Docstrings & Recoverable Error Paths**

* Refactor a tool docstring on your *own* server into a rich, guidance-oriented prompt.
* Rewrite a rigid error path (e.g., `"Error 3"`) into a **recoverable diagnostic message** (e.g., `"no docs for v4.x: latest published is v3.2..."`).
* **Verification Artifact (`error_before_after.md`):** Provide a transcript showing how the model handles the failing tool call before versus after the rewrite, demonstrating intelligent error pivoting.


#### **5. Third-Party Supply Chain Security Audit (`risk_note.md`)**

Submit an exact **5-line security evaluation** for introducing the `package-registry` server into your agent's trust boundary, addressing:

1. **Maintainer/Author Identity**
2. **Access & Reach Boundaries**
3. **Logging & Telemetry Practices**
4. **Impact of a Compromised/Stolen Token**
5. **Final Production Verdict:** Ship or Don't Ship

---

### **Evaluation Rubric & Scoring Breakdown**

| Criterion | Points | Focus Area |
| --- | --- | --- |
| **Zero-Code Server Expansion** | **30** | `agent_diff.txt` proves 0 lines changed in core agent code when adding server #2.|
| **Protocol Wire Analysis** | **25** | Raw `wire.json` (`initialize`, `tools/list`, `tools/call`) hand-annotated with correct LLM execution location.|
| **Docstring Prompting & Errors** | **20** | Tool docstring rewritten as a prompt; recoverable error tested via `error_before_after.md` transcript.|
| **Dynamic Discovery Counting** | **15** | Tool counts ($N \rightarrow M$) and names extracted directly from live `tools/list` payloads.|
| **Supply Chain Risk Audit** | **10** | `risk_note.md` exactly 5 lines addressing maintainer, access, logs, token risk, and ship decision.|

---

### **Bonus Challenge: MCP Gateway & Token Scoping**

* Place both MCP servers behind a single **Gateway/Proxy** process that handles multi-server fan-out.
* Audit every incoming `tools/call` to a unified log line detailing `caller`, `tool`, and `requested_package@version`.
* Enforce token scoping to deny access to specific tools (e.g., deprecation lookup) and verify the denial reaches the model as a recoverable protocol error.