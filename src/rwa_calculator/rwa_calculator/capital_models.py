from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class CapitalModel(BaseModel):
    """Strict public contracts for Basel III final-reform capital modules."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_decimal(self, value: Any) -> Any:
        """Serialize Decimals losslessly for API and dashboard clients."""
        if isinstance(value, Decimal):
            return str(value)
        return value


class CapitalTraceStep(CapitalModel):
    """Human-readable trace step for portfolio capital calculations."""

    step_id: str
    description: str
    formula: str | None = None
    input_values: dict[str, str] = Field(default_factory=dict)
    output_values: dict[str, str] = Field(default_factory=dict)
    rule_reference: dict[str, str | int | None] | None = None


class OutputFloorRequest(CapitalModel):
    """Aggregate output-floor request using portfolio-level RWA inputs."""

    calculation_date: date
    pre_floor_rwa: Decimal = Field(ge=Decimal("0"))
    standardised_rwa: Decimal = Field(ge=Decimal("0"))
    cet1_capital: Decimal = Field(ge=Decimal("0"))
    tier1_capital: Decimal = Field(ge=Decimal("0"))
    total_capital: Decimal = Field(ge=Decimal("0"))
    apply_transitional_cap: bool = False


class OutputFloorResponse(CapitalModel):
    """Aggregate output-floor result and capital ratios."""

    calculation_date: date
    floor_calibration: Decimal
    pre_floor_rwa: Decimal
    standardised_rwa: Decimal
    floor_requirement_rwa: Decimal
    floored_rwa_before_cap: Decimal
    transitional_cap_rwa: Decimal | None
    applicable_rwa: Decimal
    output_floor_amount: Decimal
    cet1_ratio_pre_floor: Decimal | None
    cet1_ratio: Decimal | None
    tier1_ratio: Decimal | None
    total_capital_ratio: Decimal | None
    trace: list[CapitalTraceStep] = Field(default_factory=list)


class BusinessIndicatorYear(CapitalModel):
    """One year of operational-risk business indicator components."""

    year: int | None = None
    interest_leases_dividend_component: Decimal = Field(ge=Decimal("0"))
    services_component: Decimal = Field(ge=Decimal("0"))
    financial_component: Decimal = Field(ge=Decimal("0"))


class OperationalRiskRequest(CapitalModel):
    """Operational risk standardised approach request."""

    calculation_date: date
    annual_business_indicators: list[BusinessIndicatorYear] = Field(min_length=3)
    annual_operational_losses: list[Decimal] = Field(default_factory=list)
    loss_data_quality_met: bool = True
    ilm_floor: Decimal = Field(default=Decimal("1"), ge=Decimal("1"))


class OperationalRiskResponse(CapitalModel):
    """Operational risk BI, BIC, ILM, ORC and RWA result."""

    calculation_date: date
    business_indicator: Decimal
    business_indicator_component: Decimal
    loss_component: Decimal | None
    internal_loss_multiplier: Decimal
    operational_risk_capital: Decimal
    operational_risk_rwa: Decimal
    trace: list[CapitalTraceStep] = Field(default_factory=list)


class CvaNettingSet(CapitalModel):
    """Netting set input for BA-CVA style calculations."""

    counterparty_id: str
    ead: Decimal = Field(ge=Decimal("0"))
    maturity_years: Decimal = Field(default=Decimal("1"), ge=Decimal("0"))
    risk_weight: Decimal = Field(ge=Decimal("0"))
    discount_factor: Decimal = Field(default=Decimal("1"), ge=Decimal("0"), le=Decimal("1"))


class CvaHedge(CapitalModel):
    """Eligible external CVA hedge recognised in BA-CVA full mode."""

    hedge_id: str
    effective_notional: Decimal = Field(ge=Decimal("0"))
    risk_weight: Decimal = Field(ge=Decimal("0"))
    eligible: bool = True


class SaCvaSensitivity(CapitalModel):
    """Simplified SA-CVA weighted sensitivity by risk type and bucket."""

    risk_type: str
    bucket: str
    weighted_sensitivity: Decimal
    intra_bucket_correlation: Decimal = Field(
        default=Decimal("0.50"),
        ge=Decimal("-1"),
        le=Decimal("1"),
    )


CvaApproach = Literal["AUTO", "MATERIALITY_OPTION", "BA_REDUCED", "BA_FULL", "SA_CVA"]


class CvaRiskRequest(CapitalModel):
    """CVA capital request supporting materiality, BA-CVA and SA-CVA paths."""

    calculation_date: date
    approach: CvaApproach = "AUTO"
    aggregate_non_centrally_cleared_derivative_notional: Decimal = Field(ge=Decimal("0"))
    ccr_capital_requirement: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    materiality_option_elected: bool = False
    supervisor_approved_sa_cva: bool = False
    netting_sets: list[CvaNettingSet] = Field(default_factory=list)
    eligible_hedges: list[CvaHedge] = Field(default_factory=list)
    sa_cva_sensitivities: list[SaCvaSensitivity] = Field(default_factory=list)
    alpha: Decimal = Field(default=Decimal("1.40"), gt=Decimal("0"))
    rho: Decimal = Field(default=Decimal("0.50"), ge=Decimal("0"), le=Decimal("1"))
    beta: Decimal = Field(default=Decimal("0.25"), ge=Decimal("0"), le=Decimal("1"))
    sa_cva_multiplier: Decimal = Field(default=Decimal("1.25"), gt=Decimal("0"))


class CvaRiskResponse(CapitalModel):
    """CVA capital and RWA result."""

    calculation_date: date
    approach_used: str
    cva_capital_requirement: Decimal
    cva_rwa: Decimal
    materiality_threshold_applied: bool
    hedge_benefit: Decimal
    trace: list[CapitalTraceStep] = Field(default_factory=list)


class OffBalanceSheetItem(CapitalModel):
    """Leverage-ratio off-balance sheet item with prescribed CCF."""

    item_id: str
    notional: Decimal = Field(ge=Decimal("0"))
    credit_conversion_factor: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))


class LeverageRatioRequest(CapitalModel):
    """Leverage ratio exposure measure request."""

    calculation_date: date
    tier1_capital: Decimal = Field(ge=Decimal("0"))
    on_balance_sheet_exposures: Decimal = Field(ge=Decimal("0"))
    derivative_replacement_cost: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    derivative_potential_future_exposure: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    sft_gross_exposure: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    sft_netting_benefit: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    off_balance_sheet_items: list[OffBalanceSheetItem] = Field(default_factory=list)
    tier1_deductions_eligible_for_exposure_measure: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
    )
    gsib_higher_loss_absorbency_requirement: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        le=Decimal("1"),
    )


class LeverageRatioResponse(CapitalModel):
    """Leverage ratio result."""

    calculation_date: date
    tier1_capital: Decimal
    exposure_measure: Decimal
    on_balance_sheet_component: Decimal
    derivative_component: Decimal
    sft_component: Decimal
    off_balance_sheet_component: Decimal
    leverage_ratio: Decimal | None
    minimum_leverage_ratio: Decimal
    gsib_leverage_buffer: Decimal
    leverage_ratio_surplus_or_shortfall: Decimal | None
    trace: list[CapitalTraceStep] = Field(default_factory=list)


class PortfolioCapitalRequest(CapitalModel):
    """Portfolio capital stack request combining all risk-type RWAs."""

    calculation_date: date
    credit_rwa_pre_floor: Decimal = Field(ge=Decimal("0"))
    credit_rwa_standardised: Decimal = Field(ge=Decimal("0"))
    cva_rwa: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    operational_rwa: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    market_rwa: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    securitisation_rwa: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    cet1_capital: Decimal = Field(ge=Decimal("0"))
    tier1_capital: Decimal = Field(ge=Decimal("0"))
    total_capital: Decimal = Field(ge=Decimal("0"))
    apply_output_floor_transitional_cap: bool = False


class PortfolioCapitalResponse(CapitalModel):
    """Portfolio-level capital result with aggregate output floor."""

    calculation_date: date
    credit_rwa_pre_floor: Decimal
    credit_rwa_standardised: Decimal
    cva_rwa: Decimal
    operational_rwa: Decimal
    market_rwa: Decimal
    securitisation_rwa: Decimal
    pre_floor_rwa: Decimal
    standardised_rwa: Decimal
    output_floor: OutputFloorResponse
    applicable_rwa: Decimal
    cet1_ratio: Decimal | None
    tier1_ratio: Decimal | None
    total_capital_ratio: Decimal | None
    trace: list[CapitalTraceStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_floor_alignment(self) -> PortfolioCapitalResponse:
        """Keep the top-level applicable RWA aligned with the nested output-floor module."""
        if self.applicable_rwa != self.output_floor.applicable_rwa:
            raise ValueError("applicable_rwa must match output_floor.applicable_rwa")
        return self
