# RWA Multi-Agent Architecture Notes

## Final Architecture

The RWA commentary workflow is a guarded compact LangGraph execution with a parallel worker phase and a central `SupervisorAgent`. Requests enter through a pre-graph validation layer that validates schema, rejects PII-like fields, normalizes anonymized identifiers, and constructs the initial Pydantic v2 `AgentState`.

The graph is intentionally small: `AnalysisPhase -> SupervisorAgent -> Final Output Guard`. The `AnalysisPhase` runs `DataAnalystAgent` and `RiskExpertAgent` concurrently when both only depend on the initial state. ReAct behavior is internal to each worker node: `Inspect State -> Select Action/Tool -> Execute Tool -> Observe Result -> Emit Structured Finding`.

The Supervisor is the routing brain. It checks required findings, evaluates consensus, enforces the default loop limit of 2, blocks unsafe runs, or compiles the final structured commentary. LLM Guard is applied at coarse safe boundaries: before and after each LLM-facing agent interaction and before final generated commentary is returned. Unsafe output is blocked before it can be written into `AgentState`. Langfuse observes the full execution, including graph IDs, thread IDs, node transitions, selected agents, prompt versions, tool calls, LLM calls, latency, token usage, guardrail results, blocked events, and evaluation scores. MemorySaver checkpoints `AgentState` by `thread_id` for loop persistence and human-in-the-loop readiness.

## What Changed Compared To The Previous Graph

- Added an explicit pre-graph request validation, PII guard, anonymization, and `AgentState` builder layer.
- Replaced the linear `Supervisor -> Data -> Supervisor -> Risk -> Supervisor` runtime with compact `AnalysisPhase -> Supervisor`.
- Changed LLM Guard from a single branch into input/output wrappers around LLM-facing boundaries, plus final output guard.
- Kept `SupervisorAgent` as the central routing and synthesis node with explicit outcomes: repeat analysis, Completed, LoopLimitReached, and Blocked.
- Kept ReAct steps inside worker nodes rather than as separate LangGraph nodes.
- Split deterministic tools into `DataTools` and `RiskTools`, and listed the required analysis actions.
- Added Prompt Registry as a shared dependency with Langfuse registry and local fallback modes.
- Moved Langfuse into a full-execution observability layer instead of representing it as a graph node.
- Added MemorySaver/checkpointing as state persistence tied to `thread_id`, loop execution, and intervention readiness.
- Made structured final commentary explicit: Executive Summary, CRO View, CFO View, recommended actions, validation flags, and observability metadata.

## Updated Implementation Notes

### Task 1 - Supervisor + ReAct LangGraph

- Keep `AgentState` strongly typed with `rwa_input_data`, `rwa_output_results`, `messages`, `validation_flags`, `agent_findings`, `recommended_actions`, and `commentary_views`.
- Add or preserve a pre-graph state builder that validates schema, rejects PII-like fields, normalizes anonymized identifiers, and fails fast before graph execution.
- Implement `AnalysisPhase` as the graph entry point and run independent workers concurrently.
- Implement `SupervisorAgent` as the only routing brain after worker fan-in.
- Ensure each worker records explicit ReAct steps: inspect, selected tool/action, deterministic tool execution, observation, structured finding.
- Keep ReAct steps internal to worker nodes; do not model every ReAct step as a separate LangGraph node.
- Keep quantitative checks inside deterministic Python tools only.
- Data tools must cover duplicate asset IDs, missing outputs, missing risk parameters, exposure concentration, and portfolio/sector/asset-class anomalies.
- Risk tools must cover deterministic RWA validation, movement-driver analysis, risk/capital interpretation, and Basel/internal-policy context where available.

### Task 2 - LLM Guard, Langfuse, Prompt Registry, MemorySaver

- Wrap every LLM-facing interaction with LLM Guard input and output scans.
- Never write blocked or unsafe agent output into `AgentState`.
- Persist guardrail scan results, blocked flags, and sanitized metadata into observability state.
- Fetch prompts via prompt registry abstraction. Use Langfuse Prompt Registry when enabled and local fallback when disabled.
- Required prompt names: `rwa-supervisor-agent-system`, `rwa-data-analyst-agent-system`, `rwa-risk-expert-agent-system`.
- Use Langfuse as full-execution observability, capturing graph execution ID, thread ID, node transitions, selected agents, LLM calls, tool calls, prompt versions, latency, token usage, guardrail results, blocked events, and evaluation scores.
- Required scores: `Faithfulness`, `Groundedness`, `Anomaly_Detection`, `Guardrail_Block_Count`, `PII_Detected`, `Prompt_Injection_Risk`.
- Use MemorySaver/checkpointer keyed by `thread_id` to persist graph iterations and support later human intervention.

### Task 3 - Structured UI Consumption

- The UI must consume structured fields from `MultiAgentRwaAnalysisResponse`, not raw agent text.
- Render only `commentary_views`, `final_commentary`, `recommended_actions`, `validation_flags`, and observability metadata.
- Show blocked/unavailable state if status is `BLOCKED`; do not render partial or unsafe commentary.
- Keep tabs isolated: Executive Summary, CRO View, and CFO View must read their own structured fields.
- Regenerate must trigger a new guarded LangGraph execution and replace the displayed structured payload only after safe completion.
