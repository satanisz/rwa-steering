from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class SteeringModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_decimal(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        return value


ScenarioId = Literal["BASE", "DOWNSIDE", "STRESS", "RECOVERY"]


class SteeringRequest(SteeringModel):
    as_of_date: date
    projection_dates: list[date] = Field(min_length=1)
    scenarios: list[ScenarioId] = Field(default_factory=lambda: ["BASE", "DOWNSIDE", "STRESS"])
    jurisdiction: str = "EU_CRR3_EBA"
    core_info: list[dict[str, Any]] = Field(min_length=1)
    top_n_recommendations: int = Field(default=10, ge=1, le=100)


class ScenarioRunSummary(SteeringModel):
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
    methodology: str
    jurisdiction: str
    summaries: list[ScenarioRunSummary]
    projections: list[ProjectionRow]
    attributions: list[AttributionRow]
    recommendations: list[RecommendationRow]
    limitations: list[str]
