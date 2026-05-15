from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class RATSModel(BaseModel):
    """Base model for RATS API contracts.

    Decimal serialization is kept lossless because RATS compares RWA, business cost and
    reduction notionals that are later useful in audit trails and dashboard exports.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_decimal(self, value: Any) -> Any:
        """Render Decimal fields as strings in JSON responses."""
        if isinstance(value, Decimal):
            return str(value)
        return value


ScenarioId = Literal["BASE", "DOWNSIDE", "STRESS", "RECOVERY"]


class SwarmSettings(RATSModel):
    """Hyperparameters for the deterministic Risk-Aware Trading Swarm search."""

    particles: int = Field(default=24, ge=4, le=200)
    iterations: int = Field(default=30, ge=1, le=250)
    max_stall_iterations: int = Field(default=8, ge=1, le=100)
    inertia_min: Decimal = Field(default=Decimal("0.40"), ge=Decimal("0"), le=Decimal("1"))
    inertia_max: Decimal = Field(default=Decimal("0.90"), ge=Decimal("0"), le=Decimal("1.5"))
    cognitive_weight: Decimal = Field(default=Decimal("1.40"), ge=Decimal("0"))
    social_weight: Decimal = Field(default=Decimal("1.40"), ge=Decimal("0"))
    concentration_threshold: Decimal = Field(
        default=Decimal("0.80"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )
    random_seed: int = 20260515

    @model_validator(mode="after")
    def validate_inertia_order(self) -> SwarmSettings:
        """Require the maximum inertia weight to be at least the minimum value."""
        if self.inertia_max < self.inertia_min:
            raise ValueError("inertia_max cannot be lower than inertia_min")
        return self


class RATSConstraints(RATSModel):
    """Eligibility and risk constraints applied to a candidate optimization strategy."""

    max_strategy_legs: int = Field(default=5, ge=1, le=25)
    max_total_reduction_pct: Decimal = Field(
        default=Decimal("0.25"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )
    max_single_reduction_pct: Decimal = Field(
        default=Decimal("0.50"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )
    max_business_cost: Decimal | None = Field(default=None, ge=Decimal("0"))
    min_rwa_saving: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class ObjectiveWeights(RATSModel):
    """Weights used by the risk-aware trading objective function."""

    rwa_saving: Decimal = Field(default=Decimal("1.00"), ge=Decimal("0"))
    business_cost: Decimal = Field(default=Decimal("0.10"), ge=Decimal("0"))
    concentration_penalty: Decimal = Field(default=Decimal("0.02"), ge=Decimal("0"))
    infeasibility_penalty: Decimal = Field(default=Decimal("1000000000"), ge=Decimal("0"))


class RATSRequest(RATSModel):
    """Request for risk-aware swarm optimization on forecasted RWA inputs.

    The service forecasts the supplied current portfolio to ``projection_date`` using generated
    scenario inputs, builds Unique Eligible Instruments from allowed steering actions, and runs a
    RATS/PSO search for the best eligible optimization strategy.
    """

    as_of_date: date
    projection_date: date
    scenario_id: ScenarioId = "STRESS"
    jurisdiction: str = "EU_CRR3_EBA"
    core_info: list[dict[str, Any]] = Field(min_length=1)
    top_n_candidates: int = Field(default=25, ge=1, le=100)
    constraints: RATSConstraints = Field(default_factory=RATSConstraints)
    objective_weights: ObjectiveWeights = Field(default_factory=ObjectiveWeights)
    swarm: SwarmSettings = Field(default_factory=SwarmSettings)
    request_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_projection_date(self) -> RATSRequest:
        """Require projection date to be on or after the as-of date."""
        if self.projection_date < self.as_of_date:
            raise ValueError("projection_date cannot be before as_of_date")
        return self


class RATSUEI(RATSModel):
    """Unique Eligible Instrument available to the RATS optimizer."""

    uei_id: str
    asset_id: str
    counterparty_gid: str
    entity_class: str
    sub_class: str
    action_code: str
    max_reduction_pct: Decimal
    business_cost_factor: Decimal
    projected_exposure_amount: Decimal
    projected_rwa: Decimal


class RATSStrategyLeg(RATSModel):
    """Selected optimization strategy leg returned by RATS."""

    uei_id: str
    asset_id: str
    counterparty_gid: str
    entity_class: str
    sub_class: str
    action_code: str
    reduction_pct: Decimal
    notional_reduction_amount: Decimal
    rwa_before_strategy: Decimal
    business_cost: Decimal


class RATSIteration(RATSModel):
    """One convergence point from the swarm recursion."""

    iteration: int
    global_best_objective: Decimal
    global_best_rwa_saving: Decimal
    feasible_particle_ratio: Decimal


class RATSRunSummary(RATSModel):
    """Portfolio-level summary of the best eligible RATS strategy."""

    current_rwa: Decimal
    projected_rwa_before_strategy: Decimal
    optimized_projected_rwa: Decimal
    rwa_saving: Decimal
    rwa_saving_pct: Decimal | None
    objective_value: Decimal
    total_business_cost: Decimal
    total_reduction_amount: Decimal
    selected_legs: int
    feasible: bool
    constraint_violations: list[str] = Field(default_factory=list)


class RATSResponse(RATSModel):
    """Complete RATS response for API clients and dashboards."""

    api_version: str = "v1"
    methodology: str
    rats_engine_version: str
    scenario_id: str
    as_of_date: date
    projection_date: date
    summary: RATSRunSummary
    candidates: list[RATSUEI]
    best_strategy: list[RATSStrategyLeg]
    convergence: list[RATSIteration]
    limitations: list[str]
    input_package_version: str | None = None
    input_package_validation_status: str | None = None


class ApiErrorDetail(RATSModel):
    """Stable machine-readable error detail for RATS API clients."""

    code: str
    message: str
    field_path: str | None = None
    severity: str = "ERROR"
    remediation: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(RATSModel):
    """Versioned error response returned by RATS API exception handlers."""

    api_version: str = "v1"
    error: ApiErrorDetail
