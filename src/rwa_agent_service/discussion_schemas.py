from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator

from .schemas import AgentModel, AgentSeverity

DiscussionAgentName = Literal["DataAnalystAgent", "RiskExpertAgent", "SupervisorAgent"]
DiscussionStatus = Literal["COMPLETED", "LOOP_LIMIT_REACHED", "BLOCKED"]
ParameterValue = Decimal | str | int | bool | None

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(?:\+|00)\d[\d\s().-]{7,}\d")
_PII_KEY_MARKERS = (
    "customername",
    "clientname",
    "borrowername",
    "counterpartyname",
    "legalname",
    "firstname",
    "lastname",
    "email",
    "phone",
    "address",
    "iban",
    "pesel",
    "ssn",
    "accountnumber",
    "passport",
    "nationalid",
    "taxid",
)


class RwaInputRecord(AgentModel):
    """Anonymized exposure input available to the multi-agent discussion."""

    asset_id: str = Field(min_length=1, max_length=128)
    asset_class: str = Field(min_length=1, max_length=128)
    sector: str | None = Field(default=None, max_length=128)
    exposure_amount: Decimal = Field(validation_alias=AliasChoices("exposure_amount", "ead"))
    risk_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    rating: str | None = Field(default=None, max_length=64)
    validation_status: str | None = Field(default=None, max_length=64)
    collateral_value: Decimal | None = None
    pd: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    lgd: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    maturity_years: Decimal | None = Field(default=None, ge=Decimal("0"))
    parameters: dict[str, ParameterValue] = Field(default_factory=dict)

    @field_validator("asset_id", "asset_class", "sector", "rating", "validation_status")
    @classmethod
    def reject_pii_text(cls, value: str | None) -> str | None:
        _raise_if_pii_value(value)
        return value

    @field_validator("parameters")
    @classmethod
    def reject_pii_parameters(
        cls,
        value: dict[str, ParameterValue],
    ) -> dict[str, ParameterValue]:
        _raise_if_pii_mapping(value)
        return value


class RwaOutputRecord(AgentModel):
    """Anonymized calculator output used for deterministic validation."""

    asset_id: str = Field(min_length=1, max_length=128)
    rwa_amount: Decimal = Field(validation_alias=AliasChoices("rwa_amount", "rwa"))
    previous_rwa_amount: Decimal | None = None
    exposure_amount: Decimal | None = Field(
        default=None,
        validation_alias=AliasChoices("exposure_amount", "ead"),
    )
    risk_weight: Decimal | None = Field(default=None, ge=Decimal("0"))
    capital_requirement: Decimal | None = None
    sector: str | None = Field(default=None, max_length=128)
    rating: str | None = Field(default=None, max_length=64)
    previous_rating: str | None = Field(default=None, max_length=64)
    risk_class: str | None = Field(default=None, max_length=128)
    approach: str | None = Field(default=None, max_length=128)
    parameters: dict[str, ParameterValue] = Field(default_factory=dict)

    @field_validator("asset_id", "sector", "rating", "previous_rating", "risk_class", "approach")
    @classmethod
    def reject_pii_text(cls, value: str | None) -> str | None:
        _raise_if_pii_value(value)
        return value

    @field_validator("parameters")
    @classmethod
    def reject_pii_parameters(
        cls,
        value: dict[str, ParameterValue],
    ) -> dict[str, ParameterValue]:
        _raise_if_pii_mapping(value)
        return value


class ValidationFlag(AgentModel):
    """Machine-readable validation finding produced by deterministic tools or agents."""

    code: str = Field(min_length=1, max_length=128)
    severity: AgentSeverity
    message: str = Field(min_length=1)
    asset_id: str | None = Field(default=None, max_length=128)
    source_agent: DiscussionAgentName
    requires_human_intervention: bool = False

    @field_validator("code", "message", "asset_id")
    @classmethod
    def reject_pii_text(cls, value: str | None) -> str | None:
        _raise_if_pii_value(value)
        return value


class DiscussionMessage(AgentModel):
    """One message added to the graph state by a named agent node."""

    agent_name: DiscussionAgentName
    content: str = Field(min_length=1)
    validation_codes: list[str] = Field(default_factory=list)
    requires_follow_up: bool = False

    @field_validator("content")
    @classmethod
    def reject_pii_content(cls, value: str) -> str:
        _raise_if_pii_value(value)
        return value


class ReActStep(AgentModel):
    """Auditable ReAct-style action record for one worker agent."""

    agent_name: DiscussionAgentName
    inspection: str
    selected_action: str
    tool_name: str
    observation: str


class DiscussionAgentFinding(AgentModel):
    """Structured finding produced by a ReAct worker and consumed by SupervisorAgent."""

    finding_id: str = Field(min_length=1, max_length=128)
    agent_name: DiscussionAgentName
    category: Literal["DATA_QUALITY", "PORTFOLIO_STRUCTURE", "RISK_INTERPRETATION", "CAPITAL"]
    severity: AgentSeverity
    title: str
    summary: str
    affected_asset_ids: list[str] = Field(default_factory=list)
    validation_codes: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    react_steps: list[ReActStep] = Field(default_factory=list)


class CommentaryViews(AgentModel):
    """Supervisor-owned structured commentary views for UI consumption."""

    executive_summary: str = ""
    cro_view: str = ""
    cfo_view: str = ""


class ExecutiveCommentaryPayload(AgentModel):
    """Final structured payload emitted by SupervisorAgent."""

    status: DiscussionStatus
    consensus_reached: bool
    loop_count: int = Field(ge=0)
    generated_at: datetime
    source_label: str
    executive_summary: str
    cro_view: str
    cfo_view: str
    data_quality_observations: list[str]
    risk_observations: list[str]
    quantitative_validation: list[str]
    recommended_actions: list[str]
    validation_flags: list[ValidationFlag]
    source_agents: list[DiscussionAgentName]


class GuardrailScanResult(AgentModel):
    """Input/output scanner result captured around agent execution."""

    stage: Literal["input", "output"]
    scanner_name: str
    is_valid: bool
    risk_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    action: Literal["passed", "flagged", "blocked"]
    finding: str
    agent_name: DiscussionAgentName | None = None


class PromptUsage(AgentModel):
    """Prompt registry metadata captured for one agent node execution."""

    agent_name: DiscussionAgentName
    prompt_name: str
    prompt_source: Literal["langfuse", "local_fallback"]
    prompt_version: int | str | None = None


class EvaluationScore(AgentModel):
    """Evaluation score submitted after graph execution."""

    name: str
    value: Decimal | str | int | bool
    data_type: Literal["NUMERIC", "CATEGORICAL", "BOOLEAN", "TEXT"]
    comment: str | None = None


class MultiAgentObservability(AgentModel):
    """Observable execution metadata for the multi-agent discussion workflow."""

    langfuse_enabled: bool
    trace_id: str | None = None
    callback_handler_attached: bool = False
    checkpointer: str
    prompt_usages: list[PromptUsage] = Field(default_factory=list)
    evaluation_scores: list[EvaluationScore] = Field(default_factory=list)
    guardrail_results: list[GuardrailScanResult] = Field(default_factory=list)
    guardrail_block_count: int = 0
    pii_detected: bool = False
    prompt_injection_risk: Decimal = Decimal("0")
    node_transition_count: int = 0
    llm_call_count: int = 0
    tool_call_count: int = 0
    total_token_count: int = 0


class MultiAgentRwaAnalysisRequest(AgentModel):
    """Request body for the LangGraph multi-agent RWA analysis workflow."""

    request_id: str | None = Field(default=None, max_length=128)
    rwa_input_data: list[RwaInputRecord] = Field(min_length=1)
    rwa_output_results: list[RwaOutputRecord] = Field(min_length=1)
    loop_limit: int = Field(default=3, ge=1, le=10)
    materiality_threshold: Decimal = Field(default=Decimal("0.05"), ge=Decimal("0"))


class AgentState(AgentModel):
    """Strongly typed graph state carried through the RWA discussion workflow."""

    request_id: str | None = Field(default=None, max_length=128)
    rwa_input_data: list[RwaInputRecord]
    rwa_output_results: list[RwaOutputRecord]
    messages: list[DiscussionMessage] = Field(default_factory=list)
    validation_flags: list[ValidationFlag] = Field(default_factory=list)
    agent_findings: list[DiscussionAgentFinding] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    commentary_views: CommentaryViews = Field(default_factory=CommentaryViews)
    guardrail_results: list[GuardrailScanResult] = Field(default_factory=list)
    guardrail_blocked: bool = False
    next_agent: Literal["DataAnalystAgent", "RiskExpertAgent", "END"] = "DataAnalystAgent"
    loop_count: int = Field(default=0, ge=0)
    loop_limit: int = Field(default=3, ge=1, le=10)
    materiality_threshold: Decimal = Field(default=Decimal("0.05"), ge=Decimal("0"))
    consensus_reached: bool = False
    final_commentary: ExecutiveCommentaryPayload | None = None

    @model_validator(mode="after")
    def validate_anonymized_state(self) -> AgentState:
        """Guard graph state against common PII payloads."""
        for message in self.messages:
            _raise_if_pii_value(message.content)
        for flag in self.validation_flags:
            _raise_if_pii_value(flag.message)
            _raise_if_pii_value(flag.asset_id)
        for finding in self.agent_findings:
            _raise_if_pii_value(finding.title)
            _raise_if_pii_value(finding.summary)
            for asset_id in finding.affected_asset_ids:
                _raise_if_pii_value(asset_id)
        return self

    @classmethod
    def from_request(cls, request: MultiAgentRwaAnalysisRequest) -> AgentState:
        """Create a fresh discussion state from an API request."""
        return cls(
            request_id=request.request_id,
            rwa_input_data=request.rwa_input_data,
            rwa_output_results=request.rwa_output_results,
            loop_limit=request.loop_limit,
            materiality_threshold=request.materiality_threshold,
        )


class MultiAgentRwaAnalysisResponse(AgentModel):
    """API response for the completed multi-agent RWA discussion."""

    api_version: str = "v1"
    service_version: str
    request_id: str | None = None
    run_id: str
    status: DiscussionStatus
    graph_backend: str
    final_commentary: ExecutiveCommentaryPayload
    messages: list[DiscussionMessage]
    validation_flags: list[ValidationFlag]
    agent_findings: list[DiscussionAgentFinding]
    recommended_actions: list[str]
    commentary_views: CommentaryViews
    observability: MultiAgentObservability


def _raise_if_pii_mapping(values: dict[str, ParameterValue]) -> None:
    for key, value in values.items():
        normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
        if normalized_key == "name" or any(marker in normalized_key for marker in _PII_KEY_MARKERS):
            raise ValueError(f"PII-like field is not allowed in graph state: {key}")
        _raise_if_pii_value(value)


def _raise_if_pii_value(value: ParameterValue) -> None:
    if not isinstance(value, str):
        return
    if _EMAIL_PATTERN.search(value) or _PHONE_PATTERN.search(value):
        raise ValueError("PII-like value is not allowed in graph state")
