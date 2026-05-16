from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

AgentName = Literal[
    "RWA Movement Agent",
    "Capital Stack Agent",
    "Data Quality Agent",
    "Evidence Pack Agent",
    "Board Commentary Agent",
]
AgentSeverity = Literal["INFO", "WATCH", "MATERIAL", "CRITICAL"]
AgentStatus = Literal["COMPLETED", "SKIPPED", "FAILED"]
LlmProvider = Literal["deterministic", "ollama"]
PageContext = Literal[
    "RWA_DASHBOARD",
    "SCENARIO_ANALYSIS",
    "DATA_LINEAGE",
    "REPORTS_EVIDENCE",
    "INTELLIGENCE_BRIEFING",
]
ScenarioId = Literal["BASE", "DOWNSIDE", "STRESS", "RECOVERY"]
RunStatus = Literal["COMPLETED", "PARTIAL", "FAILED"]


class AgentModel(BaseModel):
    """Strict base model for agent service API contracts."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_decimal(self, value: Any) -> Any:
        """Serialize Decimal values as strings to avoid lossy JSON conversion."""
        if isinstance(value, Decimal):
            return str(value)
        return value


class BriefingRunControls(AgentModel):
    """Bounded calculation controls for API-triggered briefing runs."""

    runoff_months: int = Field(default=12, ge=1, le=36)
    runoff_assets: int = Field(default=50, ge=1, le=300)
    forecast_assets: int = Field(default=25, ge=1, le=200)
    monte_carlo_horizon_months: int = Field(default=6, ge=1, le=36)
    monte_carlo_paths: int = Field(default=6, ge=2, le=200)
    monte_carlo_assets: int = Field(default=15, ge=1, le=100)
    steering_assets: int = Field(default=25, ge=1, le=200)
    steering_recommendations: int = Field(default=10, ge=1, le=100)
    rats_assets: int = Field(default=15, ge=1, le=100)
    rats_candidates: int = Field(default=12, ge=1, le=100)
    rats_legs: int = Field(default=4, ge=1, le=25)
    rats_particles: int = Field(default=6, ge=2, le=100)
    rats_iterations: int = Field(default=5, ge=1, le=100)


class BriefingRequest(AgentModel):
    """Request to build an RWA management briefing from prepared project data."""

    as_of_date: date
    scenario_id: ScenarioId = "STRESS"
    page_context: PageContext = "INTELLIGENCE_BRIEFING"
    model_scope: list[str] = Field(default_factory=list)
    request_id: str | None = Field(default=None, max_length=128)
    llm_provider: LlmProvider | None = None
    include_rag_context: bool = Field(default=True, validation_alias="include_rag")
    include_evidence: bool = True
    include_memory: bool = False
    controls: BriefingRunControls = Field(default_factory=BriefingRunControls)

    @field_validator("scenario_id", mode="before")
    @classmethod
    def normalize_scenario(cls, value: object) -> object:
        """Normalize scenario ids before the service uses them as package lookups."""
        return value.upper() if isinstance(value, str) else value


class MetricFact(AgentModel):
    """A scalar fact extracted from calculated dashboard artifacts."""

    name: str
    value: Decimal | str | int | bool | None
    unit: str | None = None
    source: str
    as_of_date: date | None = None
    scenario_id: str | None = None
    model: str | None = None
    description: str | None = None


class EvidenceReference(AgentModel):
    """Reference to a source artifact or calculated frame backing an agent claim."""

    source_type: str
    source_name: str
    identifier: str
    metric_name: str | None = None
    row_count: int | None = None
    sha256: str | None = None


class AgentFinding(AgentModel):
    """One material observation returned by a domain agent."""

    title: str
    severity: AgentSeverity = "INFO"
    summary: str
    metric_name: str | None = None
    metric_value: Decimal | str | int | bool | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)


class AgentResult(AgentModel):
    """Result emitted by an individual RWA domain agent."""

    agent_name: AgentName
    status: AgentStatus
    summary: str
    findings: list[AgentFinding] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("1.0"), ge=Decimal("0"), le=Decimal("1"))


class EvidenceItem(AgentModel):
    """Evidence inventory item available to the agent graph and UI."""

    artifact_id: str
    artifact_type: str
    title: str
    source_name: str
    row_count: int | None = None
    sha256: str | None = None
    summary: str


class BoardCommentary(AgentModel):
    """Board-ready narrative generated from completed agent findings."""

    executive_summary: str
    key_messages: list[str]
    risk_watchlist: list[str]
    recommended_actions: list[str]
    limitations: list[str]
    source_agent_names: list[AgentName]


class AgentTraceSpan(AgentModel):
    """Lightweight trace event returned when external tracing is disabled."""

    name: str
    status: str
    attributes: dict[str, str | int | Decimal | bool | None] = Field(default_factory=dict)


class AgentObservability(AgentModel):
    """Observability metadata for a briefing run."""

    trace_id: str
    graph_backend: str
    llm_provider: LlmProvider
    rag_backend: str
    memory_scope: str
    spans: list[AgentTraceSpan] = Field(default_factory=list)


class BriefingResponse(AgentModel):
    """Full response returned by the agent briefing endpoint."""

    api_version: str = "v1"
    service_version: str
    request_id: str | None = None
    run_id: str
    status: RunStatus = "COMPLETED"
    as_of_date: date
    scenario_id: str
    agent_results: list[AgentResult]
    board_commentary: BoardCommentary
    metric_facts: list[MetricFact]
    evidence_inventory: list[EvidenceItem]
    lineage: list[dict[str, str | int]]
    limitations: list[str]
    observability: AgentObservability


class EvidenceResponse(AgentModel):
    """Evidence-only response used by the dashboard and evidence endpoint."""

    api_version: str = "v1"
    run_id: str
    as_of_date: date
    scenario_id: str
    evidence_inventory: list[EvidenceItem]
    lineage: list[dict[str, str | int]]


class CommentaryRequest(AgentModel):
    """Request to generate commentary from already completed agent results."""

    as_of_date: date
    scenario_id: str
    agent_results: list[AgentResult] = Field(min_length=1)
    metric_facts: list[MetricFact] = Field(default_factory=list)
    llm_provider: LlmProvider | None = None


class ApiErrorDetail(AgentModel):
    """Stable machine-readable error detail for API clients."""

    code: str
    message: str
    field_path: str | None = None
    severity: str = "ERROR"
    remediation: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(AgentModel):
    """Versioned error response returned by agent API exception handlers."""

    api_version: str = "v1"
    error: ApiErrorDetail
