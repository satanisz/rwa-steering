# Executive Plan: Agentic AI Service for RWA Intelligence, Commentary and Evidence

## 1. Executive Summary

This plan defines a dedicated `rwa_agent_service` that adds controlled agentic AI capabilities to
the RWA Steering application. The service will not calculate RWA, override regulatory logic or
invent business data. Its purpose is to turn already calculated RWA outputs, model projections,
capital stack results, data-quality diagnostics and evidence metadata into explainable management
commentary, traceable analysis and structured evidence packs.

The current project already has the core calculation and dashboard foundations:

- `rwa_calculator` for Basel-aligned row-level and portfolio calculations.
- `rwa_projection_service` for closed-book run-off projection.
- `rwa_forecast_service` for Monte Carlo portfolio paths.
- `rwa_steering` for scenario projections, attribution and recommendations.
- `rwa_rats_service` for optimization over eligible actions.
- `rwa_dashboard.data.ModelRunSet` as the shared model-output contract for dashboard surfaces.
- Dashboard pages for RWA Dashboard, Scenario Analysis, Data Lineage, Reports & Evidence and RWA
  Intelligence Briefing.

The agent service will sit above those services as an explanation and evidence layer:

```text
prepared inputs
  -> calculator / projection / forecast / steering / optimizer services
  -> ModelRunSet + capital + quality + lineage
  -> agent tools
  -> LangGraph agent workflow
  -> structured commentary + evidence references
  -> dashboard agent panels and reports
```

The target user is a risk, finance, capital-management or regulatory reporting stakeholder who
needs a concise but defensible explanation of RWA movement, capital impact, data quality and
evidence lineage.

## 2. Strategic Objective

The strategic objective is to make the RWA dashboard behave like an intelligent capital steering
workbench without weakening regulatory controls.

The service must answer five business questions:

1. What changed in current and projected RWA?
2. Which model outputs are driving the management view?
3. What capital-stack consequences follow from those movements?
4. Which data-quality and evidence items support or constrain the conclusion?
5. What commentary can be safely shown to management, with clear source references?

The service is successful if it produces useful commentary that is:

- grounded in calculated project data,
- traceable to run artifacts and methodology documents,
- reproducible for the same run inputs,
- observable in monitoring,
- structured enough for dashboard rendering,
- conservative where data or model coverage is incomplete.

## 3. Non-Negotiable Boundaries

### 3.1 What Agents May Do

Agents may:

- read calculated outputs through approved tools,
- retrieve regulatory and methodology context through RAG,
- summarize, compare and explain outputs,
- identify drivers, risks, caveats and evidence references,
- produce structured commentary for the dashboard,
- produce evidence pack sections for reports,
- flag missing or inconsistent data,
- recommend human review where outputs are ambiguous.

### 3.2 What Agents Must Not Do

Agents must not:

- calculate RWA independently,
- replace calculator or projection service outputs,
- invent exposure data, ratings, sectors, capital inputs or validation results,
- mutate prepared inputs,
- write generated data files,
- bypass model services,
- call arbitrary code or filesystem tools,
- present retrieved regulatory text as a calculation result,
- claim model-risk approval,
- hide limitations or data-quality warnings.

### 3.3 RAG Boundary

RAG provides context, not numbers.

RAG may explain why a treatment, driver or evidence item matters. It must not be used as the source
of calculated RWA, projected RWA, capital ratios, optimization outcomes or validation statuses.

## 4. Target Architecture

The agent layer should be implemented as a separate Python package and service:

```text
src/
  rwa_agent_service/
    __init__.py
    config.py
    schemas.py
    service.py
    graph.py
    nodes.py
    prompts.py
    llm.py
    tools.py
    rag.py
    memory.py
    tracing.py
    fastapi_app.py
    cli.py
    py.typed

tests/
  agents/
    test_agent_schemas.py
    test_agent_tools.py
    test_agent_graph.py
    test_agent_service.py
    test_agent_fastapi.py
```

High-level runtime:

```text
rwa_dashboard
  -> POST /v1/agents/briefing/run
      -> AgentRunRequest(as_of_date, scenario_id, page_context, model_scope)
      -> RWAAgentService
          -> LangGraph workflow
          -> approved tools over rwa_dashboard.data
          -> optional Weaviate retrieval
          -> Ollama / Gemma for local model execution
          -> Langfuse tracing
      -> AgentRunResponse
  -> dashboard renders agent cards and Board Commentary
```

## 5. Module Responsibilities

### 5.1 `config.py`

Owns runtime configuration.

Required configuration:

```text
RWA_AGENT_ENABLED=true
RWA_AGENT_LLM_PROVIDER=ollama
RWA_AGENT_LLM_MODEL=gemma4:e4b
RWA_AGENT_LLM_BASE_URL=http://localhost:11434
RWA_AGENT_TIMEOUT_SECONDS=120
RWA_AGENT_MAX_CONTEXT_CHARS=12000
RWA_AGENT_RAG_ENABLED=false
RWA_AGENT_VECTOR_PROVIDER=weaviate
RWA_AGENT_WEAVIATE_URL=http://localhost:8080
RWA_AGENT_LANGFUSE_ENABLED=false
RWA_AGENT_LANGFUSE_HOST=http://localhost:3000
RWA_AGENT_MEMORY_ENABLED=false
```

Configuration principles:

- defaults must run locally with Ollama and no external network dependency,
- production-like deployments can enable Weaviate and Langfuse,
- missing optional services should degrade explicitly, not silently,
- no secrets should be hard-coded.

### 5.2 `schemas.py`

Defines stable API contracts.

Core request:

```python
class AgentRunRequest(BaseModel):
    as_of_date: date
    scenario_id: Literal["BASE", "DOWNSIDE", "STRESS", "RECOVERY"] = "STRESS"
    page_context: Literal[
        "RWA_DASHBOARD",
        "SCENARIO_ANALYSIS",
        "DATA_LINEAGE",
        "REPORTS_EVIDENCE",
        "INTELLIGENCE_BRIEFING",
    ] = "INTELLIGENCE_BRIEFING"
    model_scope: list[str] = Field(default_factory=list)
    include_rag: bool = True
    include_evidence: bool = True
    request_id: str | None = None
```

Core response:

```python
class AgentRunResponse(BaseModel):
    api_version: str = "v1"
    request_id: str
    run_id: str
    as_of_date: date
    scenario_id: str
    status: Literal["COMPLETED", "PARTIAL", "FAILED"]
    summary: CommentaryBlock
    agent_outputs: list[AgentOutput]
    evidence: list[EvidenceReference]
    data_dependencies: list[DataDependency]
    limitations: list[str]
    trace_id: str | None = None
```

Important schema rules:

- no unstructured top-level string response,
- every dashboard card must have a stable field,
- every claim should be tied to either a calculated data dependency or evidence reference,
- agent failures should be returned as structured partial outputs where possible.

### 5.3 `tools.py`

Owns approved agent tools. Tools are deterministic Python functions over project data, not free
database or filesystem access.

Initial tools:

```text
get_current_rwa_snapshot(as_of_date)
get_regulatory_capital_snapshot(as_of_date)
get_model_run_set(as_of_date, scenario_id)
get_model_summary(as_of_date, scenario_id)
get_projection_comparison(as_of_date, scenario_id)
get_sector_projection(as_of_date, scenario_id)
get_data_quality_summary()
get_data_quality_findings()
get_input_manifest()
get_lineage_summary(as_of_date, scenario_id)
get_evidence_inventory(as_of_date, scenario_id)
retrieve_methodology_context(query, filters)
```

Tool constraints:

- all tools must be read-only,
- tools must return Pydantic models or serializable dictionaries,
- tools must cap row counts for LLM context,
- tools must expose aggregate data before row-level detail,
- tools must include source labels and run inputs,
- tools must be unit tested independently from the LLM.

### 5.4 `llm.py`

Owns model provider adapters.

Initial provider:

```text
Ollama + Gemma
model: gemma4:e4b
fallback: gemma3:4b
```

Provider abstraction:

```python
class LLMClient(Protocol):
    def generate_structured(
        self,
        messages: list[AgentMessage],
        response_schema: type[BaseModel],
        *,
        timeout_seconds: int,
    ) -> BaseModel:
        ...
```

Gemma guidance:

- prefer structured JSON output over relying on native tool calling,
- keep prompts compact and strongly typed,
- include explicit "do not calculate RWA" instructions,
- validate JSON against Pydantic,
- retry only on format failures, not on data disagreements,
- record model name and prompt version in trace metadata.

### 5.5 `graph.py`

Owns LangGraph orchestration.

Initial graph:

```text
START
  -> load_context
  -> movement_agent
  -> capital_agent
  -> data_quality_agent
  -> evidence_agent
  -> board_commentary_agent
  -> validate_output
  -> END
```

The graph should be deterministic in topology. Dynamic branching may be introduced later, but the
first version should prefer explicit nodes that are easy to test and trace.

### 5.6 `nodes.py`

Owns the node implementations.

Initial nodes:

- `load_context`
- `movement_agent`
- `capital_agent`
- `data_quality_agent`
- `evidence_agent`
- `board_commentary_agent`
- `validate_output`

Each node accepts a typed state object and returns a partial state update.

### 5.7 `rag.py`

Owns retrieval from the vector store.

Initial provider:

```text
Weaviate
```

Initial indexed collections:

```text
RegulatoryMethodologyDocument
ProjectMethodologyDocument
EvidenceArtifact
ValidationReport
GeneratedInputManifest
```

Retrieval rules:

- retrieve short chunks with metadata,
- include document id, section id and source type,
- never inject untrusted text as system instructions,
- never treat retrieved text as data,
- return "no relevant context found" when confidence is low,
- support local disabled mode where RAG returns an empty context with a clear status.

### 5.8 `tracing.py`

Owns observability integration.

Primary monitoring:

```text
Langfuse
```

Optional developer debugging:

```text
LangSmith
```

Trace metadata:

- request id,
- agent run id,
- as-of date,
- scenario id,
- page context,
- model provider,
- model name,
- prompt version,
- tool calls,
- RAG query ids,
- response validation status,
- latency,
- token usage if available,
- error category.

### 5.9 `memory.py`

Owns short-term and optional long-term memory policy.

Initial memory:

- disabled by default,
- request-scoped state only,
- no persistence of user-sensitive data,
- no persistence of calculated values as permanent facts.

Later memory:

- run-scoped decisions,
- user-approved commentary preferences,
- evidence-pack assembly history,
- prompt feedback for evaluation.

Memory must always include:

- run id,
- source version,
- timestamp,
- expiry policy,
- reason for storage.

### 5.10 `fastapi_app.py`

Owns service endpoints.

Initial endpoints:

```text
GET  /v1/agents/health
POST /v1/agents/briefing/run
POST /v1/agents/commentary/run
POST /v1/agents/evidence/run
```

Health response should include:

- service status,
- enabled LLM provider,
- model name,
- RAG enabled status,
- tracing enabled status,
- memory enabled status.

## 6. Agent Design

### 6.1 RWA Movement Agent

Purpose:

- explain RWA movement across calculated models,
- compare run-off, scenario forecast, Monte Carlo, steering and RATS,
- identify model differences without claiming one model is "true".

Inputs:

- `ModelRunSet.model_summary`,
- `ModelRunSet.projection_comparison`,
- `ModelRunSet.sector_projection`,
- current RWA snapshot.

Outputs:

- movement summary,
- top model deltas,
- top sector deltas,
- caveats.

Rules:

- distinguish current, projected and optimized RWA,
- distinguish scenario forecast from Monte Carlo path,
- never merge model outputs without naming the source model,
- highlight where models answer different questions.

### 6.2 Capital Stack Agent

Purpose:

- explain capital impact, CET1, total capital ratio, leverage, CVA, operational risk and output
  floor context.

Inputs:

- regulatory capital snapshot,
- capital stack frame,
- output floor,
- leverage ratio,
- CVA and operational risk outputs.

Outputs:

- capital impact narrative,
- constraints and buffers,
- management-relevant risks.

Rules:

- do not invent capital targets,
- do not calculate regulatory ratios outside provided outputs,
- disclose if a metric is not available.

### 6.3 Data Quality Agent

Purpose:

- summarize data-quality findings and validation gates,
- identify blocking and non-blocking issues,
- explain whether commentary is limited by data quality.

Inputs:

- input manifest,
- validation report,
- data-quality flags,
- row counts.

Outputs:

- quality score narrative,
- blocking issues,
- remediation suggestions,
- evidence references.

Rules:

- never suppress blocking findings,
- distinguish prepared input gaps from model limitations,
- avoid saying "clean" unless validation actually passed.

### 6.4 Evidence Pack Agent

Purpose:

- assemble evidence references for commentary,
- map claims to source artifacts,
- support Reports & Evidence and Data Lineage pages.

Inputs:

- manifest,
- file hashes,
- validation report,
- lineage summary,
- RAG citations.

Outputs:

- evidence list,
- claim-to-evidence mapping,
- missing evidence warnings.

Rules:

- every citation must identify source type and artifact id,
- file hashes are evidence of artifact integrity, not of regulatory correctness,
- RAG references should be cited as context, not as calculated data.

### 6.5 Board Commentary Agent

Purpose:

- synthesize final dashboard commentary for management.

Inputs:

- outputs from all previous agents,
- selected page context,
- scenario id.

Outputs:

- executive summary,
- key movement bullets,
- capital implication,
- data-quality caveat,
- evidence references,
- recommended next review actions.

Rules:

- concise by default,
- no unsupported claims,
- no hidden assumptions,
- explicit limitations,
- no direct instruction to transact or change portfolio without human review.

## 7. LangGraph State Model

Initial state:

```python
class AgentGraphState(TypedDict):
    request: AgentRunRequest
    run_id: str
    calculated_context: CalculatedContext | None
    rag_context: list[RetrievedContext]
    movement_output: AgentOutput | None
    capital_output: AgentOutput | None
    data_quality_output: AgentOutput | None
    evidence_output: AgentOutput | None
    board_output: CommentaryBlock | None
    evidence: list[EvidenceReference]
    limitations: list[str]
    errors: list[AgentError]
    trace_id: str | None
```

State principles:

- state should carry typed data, not raw prompt strings,
- each node should append evidence and limitations,
- final validation should fail closed if structured output is invalid,
- partial completion is acceptable if one non-critical agent fails.

## 8. RAG Design

### 8.1 Why RAG Is Needed

RAG is needed for:

- methodology explanation,
- regulatory context,
- evidence lookup,
- report support,
- user Q&A over methodology and artifacts.

RAG is not needed for:

- calculating RWA,
- calculating projections,
- calculating capital stack,
- deciding optimization outcomes,
- validating generated input files.

### 8.2 Initial Document Sources

Initial documents:

- Basel methodology and technical specifications retained in the repository or documentation
  package.
- Project methodology plans.
- Generated input manifest.
- Validation report.
- Data lineage summary.
- Evidence pack artifacts.

Each chunk should include metadata:

```text
document_id
document_title
source_type
section_heading
version
effective_date
hash
repository_path
chunk_index
```

### 8.3 Weaviate Schema

Suggested classes:

```text
RegulatoryDocumentChunk
ProjectMethodologyChunk
EvidenceArtifactChunk
ValidationArtifactChunk
```

Core fields:

```text
text
document_id
title
source_type
section
version
effective_date
hash
path
created_at
```

### 8.4 Retrieval Strategy

Initial retrieval:

- hybrid keyword + vector search if available,
- top 3 to 5 chunks per query,
- score threshold,
- deduplicate by document and section,
- summarize retrieved context before passing it to the final commentary node.

Example queries:

```text
"Basel final reforms output floor and RWA capital stack"
"credit risk rating migration RWA impact"
"data quality validation evidence generated input manifest"
"RWA movement attribution methodology volume rating DLGD FX"
```

## 9. Tool Calling and MCP

### 9.1 Tool Calling Policy

The service should start with Python function tools. The graph controls when tools run. The LLM
should not be allowed to call arbitrary tools directly in version one.

Why:

- local Gemma may not be fully reliable for native tool calling,
- deterministic Python tools are easier to test,
- regulated workflows require predictable data access.

### 9.2 MCP Roadmap

MCP should be introduced as a controlled gateway after the first local service works.

Candidate MCP tools:

- `rwa.get_model_summary`
- `rwa.get_projection_comparison`
- `rwa.get_sector_projection`
- `rwa.get_evidence_manifest`
- `rwa.retrieve_methodology_context`
- `rwa.get_data_quality_findings`

MCP must preserve:

- authentication,
- authorization,
- read-only boundaries,
- typed schemas,
- traceability.

## 10. Observability and Monitoring

### 10.1 Langfuse

Langfuse should be the primary monitoring layer for agent runs.

Track:

- prompt versions,
- model provider and model name,
- inputs after redaction,
- outputs,
- tool calls,
- RAG retrieval ids,
- latency,
- retries,
- validation failures,
- user feedback where available.

### 10.2 LangSmith

LangSmith may be used for LangGraph debugging and experiment comparison, especially during
development. It should not replace the production trace destination unless the team explicitly
chooses it.

### 10.3 Dashboard Trace Links

The dashboard should show trace metadata in technical panels:

```text
Agent run id
Trace id
Prompt version
LLM model
RAG enabled
Generated at
Status
```

## 11. Frontend Integration

The frontend target is the `front_concept/image_agents.png` direction:

- first-class RWA Intelligence Briefing page,
- agent cards,
- status chips,
- commentary panel,
- regulatory watch / context panel,
- data-quality findings,
- evidence and traceability footer,
- board-pack style output.

The dashboard should not look like a generic chatbot. It should look like a management
intelligence workspace.

### 11.1 Dashboard Components

Initial components:

```text
Agent status cards
Board Commentary panel
RWA Movement attribution commentary
Capital implication commentary
Data Quality findings summary
Evidence references strip
Run metadata panel
Refresh commentary action
```

### 11.2 User Actions

Initial user actions:

- generate commentary for selected reporting date and scenario,
- refresh commentary,
- inspect evidence references,
- open Data Lineage page,
- open Reports & Evidence page,
- copy/download board commentary later.

### 11.3 Rendering Rules

Rendering rules:

- show calculated metrics separately from AI text,
- show agent status and trace id,
- show evidence references below commentary,
- show partial outputs if one agent fails,
- never hide data-quality limitations.

## 12. API Design

### 12.1 Health

```http
GET /v1/agents/health
```

Response:

```json
{
  "status": "ok",
  "service": "rwa-agent-service",
  "llm_provider": "ollama",
  "llm_model": "gemma4:e4b",
  "rag_enabled": false,
  "tracing_enabled": false,
  "memory_enabled": false
}
```

### 12.2 Briefing Run

```http
POST /v1/agents/briefing/run
```

Request:

```json
{
  "as_of_date": "2026-05-15",
  "scenario_id": "STRESS",
  "page_context": "INTELLIGENCE_BRIEFING",
  "include_rag": true,
  "include_evidence": true
}
```

Response should include:

- final commentary,
- individual agent outputs,
- evidence references,
- data dependencies,
- limitations,
- trace id.

### 12.3 Commentary Run

```http
POST /v1/agents/commentary/run
```

Focused endpoint for dashboard board commentary.

### 12.4 Evidence Run

```http
POST /v1/agents/evidence/run
```

Focused endpoint for evidence pack generation.

## 13. Data Contracts

The agent service should consume calculated data through the existing dashboard data layer:

```python
current_rwa_snapshot(as_of_date)
regulatory_capital_snapshot(as_of_date)
input_package_overview()
model_run_set(as_of_date, scenario_id)
```

The service should not duplicate calculation logic.

Important input frames:

- `CurrentRwaSnapshot.results`
- `CurrentRwaSnapshot.by_entity`
- `CurrentRwaSnapshot.by_sector`
- `RegulatoryCapitalDashboardData.capital_stack`
- `RegulatoryCapitalDashboardData.output_floor`
- `ModelRunSet.model_summary`
- `ModelRunSet.projection_comparison`
- `ModelRunSet.sector_projection`
- `InputPackageOverview.data_quality_summary`
- `InputPackageOverview.row_counts`

## 14. Prompt Design

Prompts should be versioned and stored in code as templates.

Prompt principles:

- start with role and hard boundaries,
- include exact data context,
- include allowed output schema,
- require citation ids for evidence-based claims,
- require "insufficient evidence" when data is missing,
- prohibit RWA calculation by the model,
- prohibit invented facts,
- require concise management language.

Example system instruction:

```text
You are an RWA intelligence agent. You explain calculated RWA outputs, capital metrics,
data-quality findings and evidence references. You do not calculate RWA. You do not invent
portfolio data. You only use the provided calculated context and retrieved evidence. If the
context does not support a claim, mark it as a limitation.
```

## 15. Output Quality Controls

### 15.1 Structured Validation

Every LLM output must pass Pydantic validation.

Validation checks:

- required fields present,
- no empty summary,
- evidence ids exist when referenced,
- no unsupported severity labels,
- no invalid model names,
- no forbidden wording from known cleanup list,
- token/character caps respected.

### 15.2 Data Grounding Checks

The service should verify:

- referenced model names exist in `ModelRunSet.model_summary`,
- referenced scenario exists,
- referenced sectors exist in `sector_projection`,
- referenced evidence ids exist in evidence list,
- data-quality limitation is included when findings exist.

### 15.3 Refusal and Partial Output

If the agent cannot produce safe commentary:

- return `PARTIAL` or `FAILED`,
- include validation errors,
- show fallback calculated summary without AI narrative,
- do not fabricate a commentary.

## 16. Security and Governance

Security requirements:

- no arbitrary filesystem access by agents,
- no unrestricted network access by agents,
- read-only tools only,
- strict request validation,
- redaction hooks for sensitive fields,
- no secrets in prompts or traces,
- disable memory by default,
- log model and prompt version.

Governance requirements:

- every generated commentary must include run id,
- every run must be reproducible from request parameters and data package version,
- every evidence reference must point to a source artifact,
- user-facing output must clearly separate calculated figures from AI commentary,
- agent output is decision support, not regulatory sign-off.

## 17. Testing Strategy

### 17.1 Unit Tests

Test:

- schemas,
- tool outputs,
- RAG disabled mode,
- prompt rendering,
- output validation,
- error handling.

### 17.2 Graph Tests

Test:

- graph compiles,
- each node updates expected state,
- partial failure handling,
- final response structure,
- deterministic behavior with a fake LLM.

### 17.3 Service Tests

Test:

- `POST /v1/agents/briefing/run`,
- health endpoint,
- invalid scenario,
- missing RAG provider,
- LLM timeout,
- malformed model output.

### 17.4 Dashboard Tests

Test:

- Intelligence Briefing page renders agent response,
- partial output is shown safely,
- evidence references appear,
- no exceptions when agent service is unavailable,
- no commentary is shown as calculated data.

### 17.5 Golden Tests

Maintain a small set of approved agent responses using a fake deterministic LLM. These tests should
assert structure and major content categories, not exact natural-language wording for real LLMs.

## 18. Implementation Roadmap

### Phase 1: Local Agent Service Foundation

Deliver:

- `rwa_agent_service` package,
- config,
- schemas,
- deterministic tools,
- fake LLM for tests,
- Ollama/Gemma adapter,
- FastAPI health endpoint,
- briefing endpoint returning structured output.

Acceptance:

- all tests pass,
- local `gemma4:e4b` can produce validated JSON,
- service can run without RAG and without Langfuse.

### Phase 2: LangGraph Workflow

Deliver:

- typed graph state,
- movement agent,
- capital agent,
- data-quality agent,
- evidence agent,
- board commentary agent,
- structured validation.

Acceptance:

- each node can be tested independently,
- graph returns `AgentRunResponse`,
- partial failure behavior works.

### Phase 3: Dashboard Integration

Deliver:

- dashboard client for agent service,
- Intelligence Briefing agent cards,
- Board Commentary panel,
- evidence strip,
- agent status and run metadata.

Acceptance:

- dashboard remains usable if agent service is down,
- no mock commentary is shown,
- generated commentary is visibly separate from calculated metrics.

### Phase 4: Weaviate RAG

Deliver:

- document ingestion pipeline,
- Weaviate schema,
- retrieval tool,
- citation metadata,
- RAG context in evidence and board commentary agents.

Acceptance:

- RAG can be disabled,
- retrieved chunks include source metadata,
- commentary can cite methodology/evidence references.

### Phase 5: Langfuse Monitoring

Deliver:

- Langfuse trace wrapper,
- trace ids in API response,
- prompt version tracking,
- tool-call metadata.

Acceptance:

- every agent run has a trace when enabled,
- sensitive values are not logged unredacted,
- dashboard can show trace id.

### Phase 6: MCP Gateway

Deliver:

- MCP server exposing approved read-only tools,
- schema-aligned tool contracts,
- optional agent service integration.

Acceptance:

- MCP tools return the same data as Python tools,
- tool calls are auditable,
- no write operations exposed.

### Phase 7: Memory

Deliver:

- request-scoped memory,
- optional run-scoped persistence,
- retention policy,
- dashboard display of memory status.

Acceptance:

- memory disabled by default,
- no calculated facts persisted without run id and source version,
- memory can be purged.

## 19. Operational Runbook

### 19.1 Local Development

Expected local stack:

```text
Ollama running on localhost:11434
Gemma model installed as gemma4:e4b
RWA dashboard running on localhost:8501
Agent service running on localhost:8030
Weaviate optional
Langfuse optional
```

### 19.2 Startup Commands

Expected commands:

```bash
ollama list
uv run rwa-agent-service --port 8030
uv run rwa-dashboard
```

### 19.3 Smoke Tests

Smoke tests:

```bash
curl http://localhost:8030/v1/agents/health
curl -X POST http://localhost:8030/v1/agents/briefing/run \
  -H "Content-Type: application/json" \
  -d "{\"as_of_date\":\"2026-05-15\",\"scenario_id\":\"STRESS\"}"
```

### 19.4 Failure Modes

Expected failures and behavior:

- Ollama unavailable: return structured service error, dashboard shows agent unavailable.
- LLM invalid JSON: retry once, then return partial output.
- RAG unavailable: continue without RAG if not required.
- Data tool failure: fail closed for that agent output.
- Langfuse unavailable: continue without tracing only if tracing is optional.

## 20. Acceptance Criteria

The first production-quality milestone is accepted when:

- agent service exists as a separate package,
- dashboard can call the service,
- `Board Commentary Agent` produces structured commentary from real calculated data,
- commentary includes limitations and evidence references,
- no generated commentary is hard-coded,
- no RWA is calculated by the LLM,
- no arbitrary tools are available to the LLM,
- all agent tools are read-only,
- local Gemma works through Ollama,
- tests use fake deterministic LLM where appropriate,
- service can run with RAG and tracing disabled,
- docs explain the RAG boundary clearly.

## 21. Key Design Decisions

1. Agentic AI is a separate service, not dashboard-only code.
2. LangGraph is the orchestration layer.
3. Gemma through Ollama is the local development LLM.
4. Weaviate is the target vector database for RAG.
5. Langfuse is the primary trace and monitoring layer.
6. LangSmith is optional for graph development and debugging.
7. MCP is a later gateway for read-only tools, not a phase-one dependency.
8. Memory is disabled by default.
9. RAG provides context and evidence, not calculated values.
10. Dashboard rendering must separate calculated metrics from AI commentary.

## 22. Planning Questions Before Implementation

These questions should be resolved before building the first full agent service:

1. Should the first service run inside the same process during local development, or always as a
   separate FastAPI process?
2. Should dashboard calls be synchronous for phase one, or should agent runs become asynchronous
   jobs with polling?
3. Which documents are approved for first RAG ingestion?
4. Should Langfuse be mandatory in the development environment or optional?
5. Should the first dashboard integration call the agent service automatically on page load or only
   after a user clicks "Generate commentary"?
6. What is the maximum acceptable response time for local Gemma commentary generation?
7. Should generated commentary be persisted as an artifact, or regenerated per dashboard session?
8. Who is the intended final audience for Board Commentary: executive board, risk committee,
   internal model validation or technical audit?

## 23. Recommended First Implementation Slice

The recommended first implementation slice is deliberately narrow:

```text
rwa_agent_service
  -> FastAPI health
  -> FastAPI briefing run
  -> fake LLM tests
  -> Ollama Gemma adapter
  -> tools over ModelRunSet, capital and quality data
  -> one LangGraph flow
  -> structured Board Commentary response
  -> dashboard Intelligence Briefing integration
```

This slice proves the architecture without forcing Weaviate, Langfuse, MCP or memory into the
critical path too early. Once the local graph is stable, RAG and tracing can be added without
rewriting the dashboard or calculation services.
