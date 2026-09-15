Week 7 Engineering Challenge: Agent Loop vs. Deterministic Workflow Benchmarking
Overview & Objective
In Week 7, the core focus shifts from basic tool execution to mastering Agentic Loops and Orchestration. Mobile/Flutter developers are tasked with designing, executing, and benchmarking two competing architectures—an Autonomous ReAct Agent and a Fixed, Deterministic Orchestration Pipeline—to resolve multi-step code and schema migration tasks.

The goal of this assignment is to move beyond AI hype and systematically evaluate whether an unpredictable, dynamic agent loop actually delivers higher accuracy or efficiency compared to a rigid, fixed workflow.

Key Technical Deliverables
1. Tool Construction & Strict Schema Definition
Implement a mandatory 3rd tool within the pipeline execution context.

Enforce strict, type-safe parameter schemas (Pydantic / Structured JSON / Tool Definitions) to guarantee reliable tool calls and prevent execution-time failures.

2. Execution Circuit Breakers & Safety Boundaries
To prevent infinite reasoning loops, runaway API costs, or thread-locking delays, developers must implement hard circuit breakers across both execution models:

Max Iteration Limits: Strict ceiling on agent reasoning loops.

Token & Cost Caps: Automatic execution abortion upon hitting predefined spending thresholds.

Time-to-Execution (p50/p99 Latency Limits): Hard timeout limits per query sequence.

3. The Head-to-Head Race (Benchmarking Run)
Run both systems through a standardized test suite of 10 complex, multi-step migration scenarios.

Collect, log, and analyze real-time performance telemetry across both architectures.

Evaluation Metrics & Final Deliverable
Developers must submit a Data-Backed Architecture Verdict proving whether an autonomous agent loop is genuinely necessary for the task, supported by the following captured metrics:

Pass / Success Rate: Total correct migrations completed without manual intervention.

p50 & p99 Latency: Processing time comparison between the dynamic loop and fixed pipeline.

Token Consumption: Input/output token overhead required to arrive at a solution.

Financial Cost: Total API expenditure per successful execution.