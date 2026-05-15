from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class ForecastModel(BaseModel):
    """Base model for forecast API contracts.

    The service emits many monetary and probability-like values. Serializing Decimals as strings
    keeps dashboard exports and later model-validation notebooks free of binary float surprises.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_decimal(self, value: Any) -> Any:
        """Render Decimal fields losslessly in JSON responses."""
        if isinstance(value, Decimal):
            return str(value)
        return value


ScenarioId = Literal["BASE", "DOWNSIDE", "STRESS", "RECOVERY"]
ForecastModelType = Literal["VAR", "LSTM_PROXY"]


class ObjectiveWeights(ForecastModel):
    """Loss-function weights used to score full Monte Carlo trajectories."""

    profit: Decimal = Field(default=Decimal("1.00"), ge=Decimal("0"))
    rwa_breach_penalty: Decimal = Field(default=Decimal("1.00"), ge=Decimal("0"))
    turnover_penalty: Decimal = Field(default=Decimal("0.02"), ge=Decimal("0"))
    drawdown_penalty: Decimal = Field(default=Decimal("0.50"), ge=Decimal("0"))
    terminal_rwa_penalty: Decimal = Field(default=Decimal("0.01"), ge=Decimal("0"))


class ForecastRequest(ForecastModel):
    """Request for autoregressive forecast and Monte Carlo path generation.

    ``core_info`` is the starting portfolio. The service forecasts market factors, generates
    stochastic portfolio trajectories and scores each path as a multi-period decision problem.
    """

    as_of_date: date
    horizon_months: int = Field(default=36, ge=1, le=60)
    path_count: int = Field(default=24, ge=1, le=500)
    model_type: ForecastModelType = "VAR"
    scenario_id: ScenarioId = "BASE"
    jurisdiction: str = "EU_CRR3_EBA"
    core_info: list[dict[str, Any]] = Field(min_length=1)
    random_seed: int = 20260515
    initial_capital_ratio: Decimal = Field(
        default=Decimal("0.145"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )
    capital_ratio_floor: Decimal = Field(
        default=Decimal("0.120"),
        gt=Decimal("0"),
        le=Decimal("1"),
    )
    retained_earnings_rate: Decimal = Field(
        default=Decimal("0.25"),
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    return_top_paths: int = Field(default=5, ge=1, le=25)
    objective_weights: ObjectiveWeights = Field(default_factory=ObjectiveWeights)
    request_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_return_top_paths(self) -> ForecastRequest:
        """Keep requested top paths within generated path count."""
        if self.return_top_paths > self.path_count:
            raise ValueError("return_top_paths cannot exceed path_count")
        return self


class MarketFactorStep(ForecastModel):
    """One simulated market-factor point in a Monte Carlo path."""

    path_id: int
    step: int
    projection_date: date
    model_type: str
    volatility_index: Decimal
    credit_spread_bps: Decimal
    yield_curve_slope_bps: Decimal
    liquidity_index: Decimal
    unemployment_proxy: Decimal
    gdp_growth_proxy: Decimal
    default_probability_proxy: Decimal
    loss_probability_proxy: Decimal


class PortfolioPathStep(ForecastModel):
    """Portfolio aggregate metrics for one step of one simulated trajectory."""

    path_id: int
    step: int
    projection_date: date
    exposure_amount: Decimal
    rwa: Decimal
    own_funds: Decimal
    capital_ratio: Decimal | None
    monthly_profit: Decimal
    cumulative_profit: Decimal
    turnover_amount: Decimal
    max_drawdown: Decimal
    rwa_breach: bool


class PathScore(ForecastModel):
    """Loss-function result for one full Monte Carlo trajectory."""

    path_id: int
    objective_value: Decimal
    cumulative_profit: Decimal
    rwa_breach_penalty: Decimal
    turnover_penalty: Decimal
    max_drawdown_penalty: Decimal
    terminal_rwa_penalty: Decimal
    min_capital_ratio: Decimal | None
    terminal_rwa: Decimal
    terminal_exposure_amount: Decimal
    total_turnover_amount: Decimal
    breached_capital_floor: bool


class ForecastSummary(ForecastModel):
    """Top-level summary of the forecast run and selected trajectory."""

    model_type: str
    scenario_id: str
    horizon_months: int
    path_count: int
    selected_path_id: int
    selected_objective_value: Decimal
    selected_terminal_rwa: Decimal
    selected_cumulative_profit: Decimal
    expected_terminal_rwa: Decimal
    p05_terminal_rwa: Decimal
    p95_terminal_rwa: Decimal
    breach_probability: Decimal


class ForecastResponse(ForecastModel):
    """Complete forecast response with factors, trajectories and path scores."""

    api_version: str = "v1"
    forecast_engine_version: str
    methodology: str
    as_of_date: date
    summary: ForecastSummary
    market_paths: list[MarketFactorStep]
    portfolio_paths: list[PortfolioPathStep]
    path_scores: list[PathScore]
    selected_path: list[PortfolioPathStep]
    limitations: list[str]
    input_package_version: str | None = None
    input_package_validation_status: str | None = None


class ApiErrorDetail(ForecastModel):
    """Stable machine-readable error detail for forecast API clients."""

    code: str
    message: str
    field_path: str | None = None
    severity: str = "ERROR"
    remediation: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ApiErrorResponse(ForecastModel):
    """Versioned error response returned by forecast API exception handlers."""

    api_version: str = "v1"
    error: ApiErrorDetail
