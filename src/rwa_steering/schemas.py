from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class SteeringModel(BaseModel):
    """Base Pydantic model for all steering API contracts.

    The strict-ish configuration keeps hackathon outputs dashboard-ready and prevents silent
    schema drift between the API, tests and future reporting exporters. Decimal values are
    serialized as strings to avoid lossy JSON float conversion.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_decimal(self, value: Any) -> Any:
        """Render Decimal fields as strings for lossless steering API responses."""
        if isinstance(value, Decimal):
            return str(value)
        return value


ScenarioId = Literal["BASE", "DOWNSIDE", "STRESS", "RECOVERY"]


class SteeringRequest(SteeringModel):
    """Input contract for a steering run.

    ``core_info`` must contain rows compatible with the existing RWA calculator. This service
    does not own regulatory calculation logic; it transforms those rows under scenario
    assumptions and repeatedly calls ``rwa_calculator``.
    """

    as_of_date: date
    projection_dates: list[date] = Field(min_length=1)
    scenarios: list[ScenarioId] = Field(default_factory=lambda: ["BASE", "DOWNSIDE", "STRESS"])
    jurisdiction: str = "EU_CRR3_EBA"
    core_info: list[dict[str, Any]] = Field(min_length=1)
    top_n_recommendations: int = Field(default=10, ge=1, le=100)
    request_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_projection_dates(self) -> SteeringRequest:
        """Require projection dates to be on or after the request as-of date."""
        invalid_dates = [item for item in self.projection_dates if item < self.as_of_date]
        if invalid_dates:
            raise ValueError("projection_dates cannot be before as_of_date")
        return self


class ScenarioRunSummary(SteeringModel):
    """Portfolio-level RWA summary for one scenario and projection date."""

    scenario_id: str
    scenario_name: str
    regime_label: str
    regime_score: Decimal
    risk_budget_multiplier: Decimal
    projection_date: date
    current_rwa: Decimal
    projected_rwa: Decimal
    rwa_delta: Decimal
    rwa_delta_pct: Decimal | None


class ProjectionRow(SteeringModel):
    """Exposure-level current versus projected RWA row.

    This shape is designed to be easy to export to CSV or feed into a dashboard. It carries the
    core steering deltas without embedding the full calculator trace.
    """

    scenario_id: str
    scenario_name: str
    jurisdiction: str
    as_of_date: date
    projection_date: date
    id: str
    counterparty_gid: str
    entity_class: str
    sub_class: str
    exposure_ccy: str
    current_exposure_amount: Decimal
    projected_exposure_amount: Decimal
    current_rating: str
    projected_rating: str
    current_dlgd: Decimal
    projected_dlgd: Decimal
    current_rwa: Decimal
    projected_rwa: Decimal
    rwa_delta: Decimal
    rwa_delta_pct: Decimal | None


class AttributionRow(SteeringModel):
    """Sequential-revaluation attribution for one portfolio scenario/date.

    Deltas are first-order driver impacts obtained by applying one projection driver at a time.
    The residual captures interactions between drivers and any logic not yet decomposed, such
    as future regulatory calendar effects.
    """

    scenario_id: str
    projection_date: date
    rwa_current: Decimal
    volume_delta: Decimal
    maturity_delta: Decimal
    rating_delta: Decimal
    dlgd_delta: Decimal
    fx_delta: Decimal
    regulatory_delta: Decimal
    interaction_or_residual_delta: Decimal
    rwa_projected: Decimal


class RecommendationRow(SteeringModel):
    """Decision-support recommendation with simulated RWA saving.

    Recommendations are intentionally not framed as automated decisions. They are ranked
    proposals for risk/finance review.
    """

    scenario_id: str
    projection_date: date
    id: str
    counterparty_gid: str
    entity_class: str
    sub_class: str
    recommended_action: str
    action_description: str
    rwa_before_action: Decimal
    rwa_after_action: Decimal
    estimated_rwa_saving: Decimal
    estimated_business_cost: Decimal
    implementation_complexity: int
    recommendation_score: Decimal
    reason_code: str


class SteeringResponse(SteeringModel):
    """Full response returned by the steering PoC endpoint."""

    api_version: str = "v1"
    methodology: str
    jurisdiction: str
    summaries: list[ScenarioRunSummary]
    projections: list[ProjectionRow]
    attributions: list[AttributionRow]
    recommendations: list[RecommendationRow]
    limitations: list[str]
    input_package_version: str | None = None
    input_package_validation_status: str | None = None


class ApiErrorDetail(SteeringModel):
    """Stable machine-readable error detail for API clients."""

    code: str
    message: str
    field_path: str | None = None
    severity: str = "ERROR"
    remediation: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(SteeringModel):
    """Versioned error response returned by steering API exception handlers."""

    api_version: str = "v1"
    error: ApiErrorDetail
