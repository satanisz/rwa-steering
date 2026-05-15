from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from rwa_calculator.paths import (
    NCCR_MAPPING_PATH,
    PREPROD_CORE_INFO_PATH,
    PREPROD_COUNTRY_INFO_PATH,
    REFERENCE_DATA_ROOT,
)
from rwa_calculator.rwa_calculator.calculator import RwaCalculator, load_core_csv
from rwa_calculator.rwa_calculator.models import ENTITY_CLASSES, EXPOSURE_SUB_CLASSES
from rwa_calculator.rwa_calculator.reference import load_nccr_mapping

PACKAGE_NAME = "rwa_steering_missing_inputs_seed"
VERSION_ID = "2026Q2_HACKATHON_SEED_V1"
SYNTHETIC_SOURCE = "synthetic_hackathon_seed"
PREPARED_CAPITAL_SOURCE = "prepared_preprod_capital_seed"
CAPITAL_PORTFOLIO_ID = "POC_BANKING_BOOK"
RANDOM_SEED = 20260515
AS_OF_DATE = date(2026, 5, 15)
YEARS = (2026, 2027, 2028, 2029, 2030)
PROJECTION_DATES = (
    AS_OF_DATE,
    date(2026, 12, 31),
    date(2027, 12, 31),
    date(2028, 12, 31),
    date(2029, 12, 31),
    date(2030, 12, 31),
)
DEFAULT_OUTPUT_ROOT = Path(__file__).with_name("generated_inputs")

GENERATED_FILE_ORDER = (
    "scenario_definitions.csv",
    "forecast_calendar.csv",
    "segment_growth_assumptions.csv",
    "rating_migration_matrix.csv",
    "dlgd_scenario_assumptions.csv",
    "fx_scenario_rates.csv",
    "macro_regime_indicators.csv",
    "regulatory_overlay_selection.csv",
    "profitability_inputs.csv",
    "steering_action_constraints.csv",
    "portfolio_strategy_limits.csv",
    "data_quality_flags.csv",
    "capital_positions.csv",
    "operational_risk_business_indicators.csv",
    "operational_risk_losses.csv",
    "cva_portfolio_inputs.csv",
    "cva_netting_sets.csv",
    "cva_hedges.csv",
    "leverage_exposures.csv",
    "leverage_off_balance_sheet_items.csv",
)


class GeneratedModel(BaseModel):
    """Strict base model for all generated missing-input rows."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    @field_serializer("*", when_used="json")
    def serialize_scalar(self, value: Any) -> Any:
        """Serialise dates and Decimals without losing audit precision."""
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, date):
            return value.isoformat()
        return value


class ScenarioDefinition(GeneratedModel):
    """Versioned scenario available to steering and projection workflows."""

    scenario_id: str
    scenario_name: str
    scenario_type: str
    severity_level: int = Field(ge=0, le=5)
    description: str
    is_active: bool
    assumption_version: str


class ForecastCalendarRow(GeneratedModel):
    """Projection calendar row tying as-of date to a future reporting horizon."""

    as_of_date: date
    projection_date: date
    projection_year: int
    projection_quarter: int = Field(ge=1, le=4)
    horizon_months: int = Field(ge=0)
    is_year_end: bool
    regulatory_year: int

    @model_validator(mode="after")
    def validate_projection_horizon(self) -> ForecastCalendarRow:
        """Ensure t0 equals as-of date and all future horizons are after t0."""
        if self.horizon_months == 0 and self.projection_date != self.as_of_date:
            raise ValueError("horizon_months=0 must point at as_of_date")
        if self.horizon_months > 0 and self.projection_date <= self.as_of_date:
            raise ValueError("projection_date must be after as_of_date")
        return self


class SegmentGrowthAssumption(GeneratedModel):
    """Segment-level balance evolution assumptions used before recalculating RWA."""

    scenario_id: str
    projection_year: int
    entity_class: str
    sub_class: str
    exposure_ccy: str
    growth_rate: Decimal
    amortization_rate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    prepayment_rate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    renewal_rate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    new_origination_rate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("entity_class")
    @classmethod
    def validate_entity_class(cls, value: str) -> str:
        """Reject segment assumptions outside calculator exposure classes."""
        if value not in ENTITY_CLASSES:
            raise ValueError(f"unknown entity_class: {value}")
        return value

    @field_validator("sub_class")
    @classmethod
    def validate_sub_class(cls, value: str) -> str:
        """Reject segment assumptions outside calculator exposure subclasses."""
        if value not in EXPOSURE_SUB_CLASSES:
            raise ValueError(f"unknown sub_class: {value}")
        return value

    @field_validator("exposure_ccy")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        """Require ISO-style currency codes."""
        if len(value) != 3 or not value.isupper():
            raise ValueError("exposure_ccy must be a three-letter uppercase code")
        return value


class RatingMigrationRow(GeneratedModel):
    """One transition probability in a scenario/year/entity rating matrix."""

    scenario_id: str
    projection_year: int
    entity_class: str
    from_rating: str
    to_rating: str
    migration_probability: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))


class DlgdScenarioAssumption(GeneratedModel):
    """Scenario shock parameters for projecting counterparty DLGD."""

    scenario_id: str
    projection_year: int
    entity_class: str
    sub_class: str
    base_multiplier: Decimal = Field(gt=Decimal("0"))
    additive_shock: Decimal
    floor: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    cap: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    collateral_haircut_multiplier: Decimal = Field(gt=Decimal("0"))

    @model_validator(mode="after")
    def validate_bounds(self) -> DlgdScenarioAssumption:
        """Ensure generated DLGD caps cannot sit below floors."""
        if self.cap < self.floor:
            raise ValueError("cap cannot be below floor")
        return self


class FxScenarioRate(GeneratedModel):
    """Synthetic FX rate for translating exposure to reporting currency."""

    scenario_id: str
    projection_date: date
    from_ccy: str
    to_ccy: str
    fx_rate: Decimal = Field(gt=Decimal("0"))
    fx_shock_pct: Decimal
    source: str


class MacroRegimeIndicator(GeneratedModel):
    """Rule-based macro regime features inspired by the steering PoC article."""

    scenario_id: str
    projection_date: date
    volatility_index: Decimal = Field(ge=Decimal("0"))
    credit_spread_bps: Decimal = Field(ge=Decimal("0"))
    yield_curve_slope_bps: Decimal
    liquidity_index: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    unemployment_proxy: Decimal = Field(ge=Decimal("0"))
    gdp_growth_proxy: Decimal
    regime_label: str
    regime_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))


class RegulatoryOverlaySelection(GeneratedModel):
    """Portfolio-to-jurisdiction mapping for applying regulatory overlays."""

    portfolio_id: str
    legal_entity_id: str
    jurisdiction_overlay: str
    reporting_currency: str
    application_date: date
    output_floor_enabled: bool
    national_discretion_profile: str


class ProfitabilityInput(GeneratedModel):
    """Synthetic profitability proxy for steering recommendations."""

    id: str
    net_revenue: Decimal
    funding_cost: Decimal
    expected_loss: Decimal
    operating_cost: Decimal
    capital_cost_rate: Decimal = Field(ge=Decimal("0"))
    raroc: Decimal
    relationship_value_score: int = Field(ge=1, le=100)
    strategic_importance_score: int = Field(ge=1, le=100)


class SteeringActionConstraint(GeneratedModel):
    """Allowed steering action and implementation metadata for one segment."""

    entity_class: str
    sub_class: str
    rating_band: str
    action_code: str
    is_allowed: bool
    max_exposure_reduction_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    min_notice_months: int = Field(ge=0)
    implementation_complexity: int = Field(ge=1, le=5)
    business_cost_factor: Decimal = Field(ge=Decimal("0"))
    requires_credit_approval: bool
    requires_client_consent: bool


class PortfolioStrategyLimit(GeneratedModel):
    """Segment-level portfolio guardrail used to avoid unrealistic recommendations."""

    portfolio_id: str
    scenario_id: str
    projection_year: int
    entity_class: str
    sub_class: str
    max_rwa_growth_pct: Decimal
    max_exposure_growth_pct: Decimal
    min_raroc: Decimal
    max_single_counterparty_concentration_pct: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    target_rwa_density: Decimal = Field(gt=Decimal("0"))


class DataQualityFlag(GeneratedModel):
    """Synthetic row-level data quality issue for remediation recommendations."""

    id: str
    field_name: str
    quality_issue_code: str
    severity: int = Field(ge=1, le=5)
    is_blocking: bool
    recommended_fix: str


class CapitalPosition(GeneratedModel):
    """Prepared capital numerator inputs for portfolio-level Basel ratios."""

    portfolio_id: str
    calculation_date: date
    cet1_capital: Decimal = Field(ge=Decimal("0"))
    tier1_capital: Decimal = Field(ge=Decimal("0"))
    total_capital: Decimal = Field(ge=Decimal("0"))
    gsib_higher_loss_absorbency_requirement: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    source: str


class OperationalRiskBusinessIndicatorInput(GeneratedModel):
    """Prepared annual business indicator components for operational risk."""

    portfolio_id: str
    year: int
    interest_leases_dividend_component: Decimal = Field(ge=Decimal("0"))
    services_component: Decimal = Field(ge=Decimal("0"))
    financial_component: Decimal = Field(ge=Decimal("0"))
    source: str


class OperationalRiskLossInput(GeneratedModel):
    """Prepared annual operational loss input for ILM calculation."""

    portfolio_id: str
    year: int
    annual_operational_loss: Decimal = Field(ge=Decimal("0"))
    loss_data_quality_met: bool
    source: str


class CvaPortfolioInput(GeneratedModel):
    """Prepared portfolio-level CVA approach and parameter inputs."""

    portfolio_id: str
    calculation_date: date
    approach: str
    aggregate_non_centrally_cleared_derivative_notional: Decimal = Field(ge=Decimal("0"))
    ccr_capital_requirement: Decimal = Field(ge=Decimal("0"))
    materiality_option_elected: bool
    supervisor_approved_sa_cva: bool
    alpha: Decimal = Field(gt=Decimal("0"))
    rho: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    beta: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    sa_cva_multiplier: Decimal = Field(gt=Decimal("0"))
    source: str


class CvaNettingSetInput(GeneratedModel):
    """Prepared CVA netting set used by BA-CVA calculation paths."""

    portfolio_id: str
    counterparty_id: str
    ead: Decimal = Field(ge=Decimal("0"))
    maturity_years: Decimal = Field(ge=Decimal("0"))
    risk_weight: Decimal = Field(ge=Decimal("0"))
    discount_factor: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))


class CvaHedgeInput(GeneratedModel):
    """Prepared eligible CVA hedge input."""

    portfolio_id: str
    hedge_id: str
    effective_notional: Decimal = Field(ge=Decimal("0"))
    risk_weight: Decimal = Field(ge=Decimal("0"))
    eligible: bool


class LeverageExposureInput(GeneratedModel):
    """Prepared leverage exposure measure components."""

    portfolio_id: str
    calculation_date: date
    on_balance_sheet_exposures: Decimal = Field(ge=Decimal("0"))
    derivative_replacement_cost: Decimal = Field(ge=Decimal("0"))
    derivative_potential_future_exposure: Decimal = Field(ge=Decimal("0"))
    sft_gross_exposure: Decimal = Field(ge=Decimal("0"))
    sft_netting_benefit: Decimal = Field(ge=Decimal("0"))
    tier1_deductions_eligible_for_exposure_measure: Decimal = Field(ge=Decimal("0"))
    source: str


class LeverageOffBalanceSheetItemInput(GeneratedModel):
    """Prepared off-balance sheet leverage exposure item."""

    portfolio_id: str
    item_id: str
    notional: Decimal = Field(ge=Decimal("0"))
    credit_conversion_factor: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))


class GeneratedInputManifest(GeneratedModel):
    """Manifest describing generated missing-input package contents and hashes."""

    package_name: str
    version_id: str
    generated_on: date
    random_seed: int
    production_ready: bool
    source_files: list[str]
    generated_files: list[str]
    row_counts: dict[str, int]
    file_sha256: dict[str, str]
    validation_status: str
    known_limitations: list[str]


def generate_missing_inputs(
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
) -> GeneratedInputManifest:
    """Generate, validate, and write the complete missing-input package."""
    output_path = Path(output_root)
    output_path.mkdir(parents=True, exist_ok=True)

    core_rows = load_core_csv(PREPROD_CORE_INFO_PATH)
    nccr_mapping = load_nccr_mapping(NCCR_MAPPING_PATH)
    calculator_payload = RwaCalculator.from_files(
        NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH
    ).calculate_batch(core_rows)
    if calculator_payload["errors"]:
        raise ValueError(
            "Cannot generate profitability for invalid core rows: "
            f"{calculator_payload['errors'][:3]}"
        )

    context = GenerationContext(
        core_rows=core_rows,
        calculator_results={str(row["id"]): row for row in calculator_payload["results"]},
        rating_scale=sorted(nccr_mapping.keys(), key=Decimal),
        segments=sorted(
            {(row["entity_class"], row["sub_class"], row["exposure_ccy"]) for row in core_rows}
        ),
        segment_pairs=sorted({(row["entity_class"], row["sub_class"]) for row in core_rows}),
        currencies=sorted({row["exposure_ccy"] for row in core_rows} | {"EUR"}),
    )

    file_rows: dict[str, list[Any]] = {
        "scenario_definitions.csv": build_scenario_definitions(),
        "forecast_calendar.csv": build_forecast_calendar(),
        "segment_growth_assumptions.csv": build_segment_growth_assumptions(context),
        "rating_migration_matrix.csv": build_rating_migration_matrix(context),
        "dlgd_scenario_assumptions.csv": build_dlgd_scenario_assumptions(context),
        "fx_scenario_rates.csv": build_fx_scenario_rates(context),
        "macro_regime_indicators.csv": build_macro_regime_indicators(),
        "regulatory_overlay_selection.csv": build_regulatory_overlay_selection(),
        "profitability_inputs.csv": build_profitability_inputs(context),
        "steering_action_constraints.csv": build_steering_action_constraints(context),
        "portfolio_strategy_limits.csv": build_portfolio_strategy_limits(context),
        "data_quality_flags.csv": build_data_quality_flags(context),
        "capital_positions.csv": build_capital_positions(context),
        "operational_risk_business_indicators.csv": build_operational_business_indicators(context),
        "operational_risk_losses.csv": build_operational_risk_losses(context),
        "cva_portfolio_inputs.csv": build_cva_portfolio_inputs(context),
        "cva_netting_sets.csv": build_cva_netting_sets(context),
        "cva_hedges.csv": build_cva_hedges(context),
        "leverage_exposures.csv": build_leverage_exposures(context),
        "leverage_off_balance_sheet_items.csv": build_leverage_off_balance_sheet_items(context),
    }
    validate_generated_package(file_rows, context)

    for file_name in GENERATED_FILE_ORDER:
        write_csv(output_path / file_name, file_rows[file_name])

    readme_path = output_path / "README.md"
    readme_path.write_text(build_readme(), encoding="utf-8")

    validation_report = build_validation_report(file_rows)
    report_path = output_path / "validation_report.json"
    report_path.write_text(
        json.dumps(validation_report, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    row_counts = {file_name: len(rows) for file_name, rows in file_rows.items()}
    generated_files = [*GENERATED_FILE_ORDER, "README.md", "validation_report.json"]
    file_sha256 = {name: sha256_file(output_path / name) for name in generated_files}
    manifest = GeneratedInputManifest(
        package_name=PACKAGE_NAME,
        version_id=VERSION_ID,
        generated_on=AS_OF_DATE,
        random_seed=RANDOM_SEED,
        production_ready=False,
        source_files=[
            relative_repo_path(PREPROD_CORE_INFO_PATH),
            relative_repo_path(PREPROD_COUNTRY_INFO_PATH),
            relative_repo_path(NCCR_MAPPING_PATH),
            relative_repo_path(REFERENCE_DATA_ROOT / "manifest.json"),
        ],
        generated_files=generated_files,
        row_counts=row_counts,
        file_sha256=file_sha256,
        validation_status="PASSED",
        known_limitations=[
            "Generated pre-production seed, not production customer or market data.",
            "FX rates and macro regimes are deterministic prepared scenario inputs.",
            (
                "Profitability and capital-management values are prepared generated inputs "
                "and require finance-system replacement before production."
            ),
            "Rating migration matrices are auditable generated assumptions, not calibrated models.",
        ],
    )
    (output_path / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return manifest


class GenerationContext(BaseModel):
    """In-memory source data used by all deterministic generated-input builders."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    core_rows: list[dict[str, str]]
    calculator_results: dict[str, dict[str, Any]]
    rating_scale: list[str]
    segments: list[tuple[str, str, str]]
    segment_pairs: list[tuple[str, str]]
    currencies: list[str]


def build_scenario_definitions() -> list[ScenarioDefinition]:
    """Create the four seed scenario definitions from the executive plan."""
    return [
        ScenarioDefinition(
            scenario_id="BASE",
            scenario_name="Base case",
            scenario_type="business_as_usual",
            severity_level=1,
            description="Expected portfolio evolution under normal credit conditions.",
            is_active=True,
            assumption_version=VERSION_ID,
        ),
        ScenarioDefinition(
            scenario_id="DOWNSIDE",
            scenario_name="Downside",
            scenario_type="macro_credit_downside",
            severity_level=2,
            description="Mild credit deterioration with moderate downgrade pressure.",
            is_active=True,
            assumption_version=VERSION_ID,
        ),
        ScenarioDefinition(
            scenario_id="STRESS",
            scenario_name="Stress",
            scenario_type="macro_credit_stress",
            severity_level=3,
            description="Severe but plausible credit stress with broad downgrade and LGD pressure.",
            is_active=True,
            assumption_version=VERSION_ID,
        ),
        ScenarioDefinition(
            scenario_id="RECOVERY",
            scenario_name="Recovery",
            scenario_type="macro_credit_recovery",
            severity_level=0,
            description="Improving credit environment with selective rating upgrades.",
            is_active=True,
            assumption_version=VERSION_ID,
        ),
    ]


def build_forecast_calendar() -> list[ForecastCalendarRow]:
    """Create t0 plus year-end projection dates through the output-floor phase-in."""
    rows: list[ForecastCalendarRow] = []
    for projection_date in PROJECTION_DATES:
        horizon_months = (
            (projection_date.year - AS_OF_DATE.year) * 12 + projection_date.month - AS_OF_DATE.month
        )
        rows.append(
            ForecastCalendarRow(
                as_of_date=AS_OF_DATE,
                projection_date=projection_date,
                projection_year=projection_date.year,
                projection_quarter=(projection_date.month - 1) // 3 + 1,
                horizon_months=horizon_months,
                is_year_end=projection_date.month == 12 and projection_date.day == 31,
                regulatory_year=projection_date.year,
            )
        )
    return rows


def build_segment_growth_assumptions(
    context: GenerationContext,
) -> list[SegmentGrowthAssumption]:
    """Generate segment balance assumptions for every scenario/year/segment."""
    rows: list[SegmentGrowthAssumption] = []
    for scenario in scenario_ids():
        for year in YEARS:
            for entity_class, sub_class, exposure_ccy in context.segments:
                noise = deterministic_decimal("growth", scenario, year, entity_class, sub_class)
                growth = base_growth(scenario, entity_class) + noise
                amortization = Decimal("0.015") + deterministic_decimal(
                    "amort",
                    scenario,
                    year,
                    sub_class,
                    min_value=Decimal("0"),
                    max_value=Decimal("0.030"),
                )
                prepayment = Decimal("0.005") + deterministic_decimal(
                    "prepay",
                    scenario,
                    year,
                    exposure_ccy,
                    min_value=Decimal("0"),
                    max_value=Decimal("0.020"),
                )
                renewal = renewal_rate(scenario, entity_class)
                new_origination = max(Decimal("0"), growth) * Decimal("0.60")
                rows.append(
                    SegmentGrowthAssumption(
                        scenario_id=scenario,
                        projection_year=year,
                        entity_class=entity_class,
                        sub_class=sub_class,
                        exposure_ccy=exposure_ccy,
                        growth_rate=q4(growth),
                        amortization_rate=q4(amortization),
                        prepayment_rate=q4(prepayment),
                        renewal_rate=q4(renewal),
                        new_origination_rate=q4(new_origination),
                    )
                )
    return rows


def build_rating_migration_matrix(context: GenerationContext) -> list[RatingMigrationRow]:
    """Generate auditable rating migration matrices with probabilities summing to one."""
    rows: list[RatingMigrationRow] = []
    for scenario in scenario_ids():
        for year in YEARS:
            for entity_class in sorted(ENTITY_CLASSES):
                for from_rating in context.rating_scale:
                    distribution = migration_distribution(
                        context.rating_scale, scenario, entity_class, from_rating
                    )
                    rows.extend(
                        RatingMigrationRow(
                            scenario_id=scenario,
                            projection_year=year,
                            entity_class=entity_class,
                            from_rating=from_rating,
                            to_rating=to_rating,
                            migration_probability=probability,
                        )
                        for to_rating, probability in distribution.items()
                    )
    return rows


def build_dlgd_scenario_assumptions(
    context: GenerationContext,
) -> list[DlgdScenarioAssumption]:
    """Generate DLGD multipliers and shocks by scenario/year/segment."""
    rows: list[DlgdScenarioAssumption] = []
    for scenario in scenario_ids():
        for year in YEARS:
            for entity_class, sub_class in context.segment_pairs:
                multiplier, shock, haircut = dlgd_parameters(scenario, entity_class, sub_class)
                rows.append(
                    DlgdScenarioAssumption(
                        scenario_id=scenario,
                        projection_year=year,
                        entity_class=entity_class,
                        sub_class=sub_class,
                        base_multiplier=q4(multiplier),
                        additive_shock=q4(shock),
                        floor=Decimal("0.0200"),
                        cap=Decimal("0.9500"),
                        collateral_haircut_multiplier=q4(haircut),
                    )
                )
    return rows


def build_fx_scenario_rates(context: GenerationContext) -> list[FxScenarioRate]:
    """Generate synthetic EUR reporting FX scenario paths for observed currencies."""
    base_rates = {
        "EUR": Decimal("1.0000"),
        "USD": Decimal("0.9200"),
        "GBP": Decimal("1.1600"),
        "PLN": Decimal("0.2300"),
        "CHF": Decimal("1.0400"),
        "SEK": Decimal("0.0890"),
    }
    rows: list[FxScenarioRate] = []
    for scenario in scenario_ids():
        for projection_date in PROJECTION_DATES:
            years_forward = Decimal(str(max(projection_date.year - AS_OF_DATE.year, 0)))
            for currency in context.currencies:
                base_rate = base_rates.get(currency, Decimal("1.0000"))
                shock = fx_shock(scenario, currency)
                drift = years_forward * Decimal("0.005")
                rows.append(
                    FxScenarioRate(
                        scenario_id=scenario,
                        projection_date=projection_date,
                        from_ccy=currency,
                        to_ccy="EUR",
                        fx_rate=q6(base_rate * (Decimal("1") + shock + drift)),
                        fx_shock_pct=q4(shock),
                        source=SYNTHETIC_SOURCE,
                    )
                )
    return rows


def build_macro_regime_indicators() -> list[MacroRegimeIndicator]:
    """Generate rule-based macro regime rows for every scenario/date."""
    rows: list[MacroRegimeIndicator] = []
    for scenario in scenario_ids():
        for projection_date in PROJECTION_DATES:
            year_step = Decimal(str(max(projection_date.year - AS_OF_DATE.year, 0)))
            volatility, spread, slope, liquidity, unemployment, gdp = macro_values(
                scenario, year_step
            )
            rows.append(
                MacroRegimeIndicator(
                    scenario_id=scenario,
                    projection_date=projection_date,
                    volatility_index=q2(volatility),
                    credit_spread_bps=q2(spread),
                    yield_curve_slope_bps=q2(slope),
                    liquidity_index=q4(liquidity),
                    unemployment_proxy=q4(unemployment),
                    gdp_growth_proxy=q4(gdp),
                    regime_label=regime_label(spread, volatility, slope, scenario),
                    regime_score=q4(regime_score(scenario)),
                )
            )
    return rows


def build_regulatory_overlay_selection() -> list[RegulatoryOverlaySelection]:
    """Map seed portfolios to the jurisdiction overlays already present in reference data."""
    return [
        RegulatoryOverlaySelection(
            portfolio_id="POC_EU_BANKING_BOOK",
            legal_entity_id="LE_EU_001",
            jurisdiction_overlay="EU_CRR3_EBA",
            reporting_currency="EUR",
            application_date=date(2025, 1, 1),
            output_floor_enabled=True,
            national_discretion_profile="EU_CRR3_SEED",
        ),
        RegulatoryOverlaySelection(
            portfolio_id="POC_UK_BANKING_BOOK",
            legal_entity_id="LE_UK_001",
            jurisdiction_overlay="UK_PRA_BASEL_3_1",
            reporting_currency="GBP",
            application_date=date(2027, 1, 1),
            output_floor_enabled=True,
            national_discretion_profile="UK_PRA_SEED",
        ),
        RegulatoryOverlaySelection(
            portfolio_id="POC_CH_BANKING_BOOK",
            legal_entity_id="LE_CH_001",
            jurisdiction_overlay="CH_FINMA_BASEL_III_FINAL",
            reporting_currency="CHF",
            application_date=date(2025, 1, 1),
            output_floor_enabled=True,
            national_discretion_profile="CH_FINMA_SEED",
        ),
    ]


def build_profitability_inputs(context: GenerationContext) -> list[ProfitabilityInput]:
    """Generate one profitability proxy row for each synthetic core exposure."""
    operating_rates = {
        "SOV": Decimal("0.0008"),
        "PSE": Decimal("0.0010"),
        "MDB": Decimal("0.0010"),
        "BANK": Decimal("0.0015"),
        "FI": Decimal("0.0018"),
        "CORP": Decimal("0.0030"),
        "RETAIL": Decimal("0.0060"),
        "OTHER": Decimal("0.0040"),
    }
    funding_rates = {
        "EUR": Decimal("0.018"),
        "USD": Decimal("0.025"),
        "GBP": Decimal("0.023"),
        "CHF": Decimal("0.012"),
        "PLN": Decimal("0.035"),
        "SEK": Decimal("0.017"),
    }
    rows: list[ProfitabilityInput] = []
    for core_row in context.core_rows:
        result = context.calculator_results[str(core_row["id"])]
        exposure = Decimal(core_row["exposure_amount"])
        expected_yield = Decimal(core_row["expected_yield"] or "0")
        pd = Decimal(str(result["basel_3_1_pd"]))
        dlgd = Decimal(str(result["basel_3_1_dlgd"]))
        rwa = Decimal(str(result["basel_3_1_rwa_final"]))
        capital = rwa * Decimal("0.08")
        net_revenue = exposure * expected_yield
        funding_cost = exposure * funding_rates.get(core_row["exposure_ccy"], Decimal("0.020"))
        expected_loss = exposure * pd * dlgd
        operating_cost = exposure * operating_rates.get(core_row["entity_class"], Decimal("0.003"))
        profit = net_revenue - funding_cost - expected_loss - operating_cost
        raroc = Decimal("0") if capital == 0 else profit / capital
        rows.append(
            ProfitabilityInput(
                id=str(core_row["id"]),
                net_revenue=q2(net_revenue),
                funding_cost=q2(funding_cost),
                expected_loss=q2(expected_loss),
                operating_cost=q2(operating_cost),
                capital_cost_rate=Decimal("0.1200"),
                raroc=q4(raroc),
                relationship_value_score=deterministic_int(
                    "rel", core_row["id"], minimum=1, maximum=100
                ),
                strategic_importance_score=deterministic_int(
                    "strat", core_row["id"], minimum=1, maximum=100
                ),
            )
        )
    return rows


def build_steering_action_constraints(
    context: GenerationContext,
) -> list[SteeringActionConstraint]:
    """Generate action availability rules for observed segments and rating bands."""
    actions = ("REDUCE_EXPOSURE", "REPRICE", "COLLATERAL_ENHANCEMENT", "NON_RENEWAL", "SELL_DOWN")
    rating_bands = ("INVESTMENT_GRADE", "HIGH_YIELD", "NOT_RATED")
    rows: list[SteeringActionConstraint] = []
    for entity_class, sub_class in context.segment_pairs:
        for rating_band in rating_bands:
            for action in actions:
                allowed = action_allowed(entity_class, sub_class, action)
                rows.append(
                    SteeringActionConstraint(
                        entity_class=entity_class,
                        sub_class=sub_class,
                        rating_band=rating_band,
                        action_code=action,
                        is_allowed=allowed,
                        max_exposure_reduction_pct=q4(
                            max_reduction(entity_class, rating_band, action, allowed)
                        ),
                        min_notice_months=notice_months(action, entity_class),
                        implementation_complexity=complexity(action, entity_class),
                        business_cost_factor=q4(business_cost_factor(action, rating_band)),
                        requires_credit_approval=action
                        in {"REPRICE", "COLLATERAL_ENHANCEMENT", "NON_RENEWAL"},
                        requires_client_consent=action in {"REPRICE", "COLLATERAL_ENHANCEMENT"},
                    )
                )
    return rows


def build_portfolio_strategy_limits(
    context: GenerationContext,
) -> list[PortfolioStrategyLimit]:
    """Generate strategy guardrails for each scenario/year/segment pair."""
    rows: list[PortfolioStrategyLimit] = []
    for scenario in scenario_ids():
        for year in YEARS:
            for entity_class, sub_class in context.segment_pairs:
                rows.append(
                    PortfolioStrategyLimit(
                        portfolio_id="POC_BANKING_BOOK",
                        scenario_id=scenario,
                        projection_year=year,
                        entity_class=entity_class,
                        sub_class=sub_class,
                        max_rwa_growth_pct=q4(max_rwa_growth(scenario, entity_class)),
                        max_exposure_growth_pct=q4(max_exposure_growth(scenario, entity_class)),
                        min_raroc=q4(min_raroc(scenario, entity_class)),
                        max_single_counterparty_concentration_pct=Decimal("0.1000"),
                        target_rwa_density=q4(target_rwa_density(entity_class, sub_class)),
                    )
                )
    return rows


def build_data_quality_flags(context: GenerationContext) -> list[DataQualityFlag]:
    """Generate synthetic but row-consistent data quality flags for demo remediation."""
    flags: list[DataQualityFlag] = []
    seen: set[tuple[str, str, str]] = set()
    for row in context.core_rows:
        if len(flags) >= 120:
            break
        row_id = str(row["id"])
        maybe_add_quality_flag(
            flags,
            seen,
            row_id,
            "counterparty_external_rating",
            "MISSING_EXTERNAL_RATING",
            3,
            False,
            "Confirm eligible ECAI rating or keep exposure on unrated treatment.",
            row["counterparty_external_rating"] == "" and row["trade_external_rating"] == "",
        )
        maybe_add_quality_flag(
            flags,
            seen,
            row_id,
            "original_maturity",
            "SUSPICIOUS_MATURITY",
            2,
            False,
            "Review contractual maturity and repayment schedule.",
            Decimal(row["original_maturity"]) > Decimal("9.0")
            or Decimal(row["residual_maturity"]) < Decimal("0.25"),
        )
        maybe_add_quality_flag(
            flags,
            seen,
            row_id,
            "govt_guarantee_flag",
            "REGULATORY_FLAG_UNCONFIRMED",
            4,
            True,
            "Attach guarantee eligibility evidence before relying on substitution.",
            row["govt_guarantee_flag"] == "Y"
            and deterministic_int("guarantee", row_id, minimum=1, maximum=5) == 1,
        )
        maybe_add_quality_flag(
            flags,
            seen,
            row_id,
            "expected_yield",
            "MISSING_PROFITABILITY",
            2,
            False,
            "Replace synthetic profitability proxy with finance-system feed.",
            deterministic_int("profitability", row_id, minimum=1, maximum=20) == 1,
        )
    return flags[:120]


def build_capital_positions(context: GenerationContext) -> list[CapitalPosition]:
    """Generate prepared capital numerator inputs for the pre-prod portfolio."""
    credit_pre_floor = portfolio_rwa(context, "basel_3_1_rwa_foundation")
    capital_base = credit_pre_floor * Decimal("1.18")
    return [
        CapitalPosition(
            portfolio_id=CAPITAL_PORTFOLIO_ID,
            calculation_date=AS_OF_DATE,
            cet1_capital=q2(capital_base * Decimal("0.145")),
            tier1_capital=q2(capital_base * Decimal("0.165")),
            total_capital=q2(capital_base * Decimal("0.185")),
            gsib_higher_loss_absorbency_requirement=Decimal("0.0100"),
            source=PREPARED_CAPITAL_SOURCE,
        )
    ]


def build_operational_business_indicators(
    context: GenerationContext,
) -> list[OperationalRiskBusinessIndicatorInput]:
    """Generate prepared three-year BI component rows for operational risk."""
    total_exposure = portfolio_exposure(context)
    base_bi = total_exposure * Decimal("0.035")
    annual_scalars = {
        AS_OF_DATE.year - 2: Decimal("0.970"),
        AS_OF_DATE.year - 1: Decimal("1.020"),
        AS_OF_DATE.year: Decimal("1.000"),
    }
    component_splits = {
        AS_OF_DATE.year - 2: (Decimal("0.52"), Decimal("0.34"), Decimal("0.14")),
        AS_OF_DATE.year - 1: (Decimal("0.54"), Decimal("0.33"), Decimal("0.13")),
        AS_OF_DATE.year: (Decimal("0.51"), Decimal("0.35"), Decimal("0.14")),
    }
    rows: list[OperationalRiskBusinessIndicatorInput] = []
    for year, scalar in annual_scalars.items():
        ildc_share, services_share, financial_share = component_splits[year]
        annual_bi = base_bi * scalar
        rows.append(
            OperationalRiskBusinessIndicatorInput(
                portfolio_id=CAPITAL_PORTFOLIO_ID,
                year=year,
                interest_leases_dividend_component=q2(annual_bi * ildc_share),
                services_component=q2(annual_bi * services_share),
                financial_component=q2(annual_bi * financial_share),
                source=PREPARED_CAPITAL_SOURCE,
            )
        )
    return rows


def build_operational_risk_losses(context: GenerationContext) -> list[OperationalRiskLossInput]:
    """Generate prepared ten-year annual operational loss rows."""
    total_exposure = portfolio_exposure(context)
    base_bi = total_exposure * Decimal("0.035")
    rows: list[OperationalRiskLossInput] = []
    for year in range(AS_OF_DATE.year - 9, AS_OF_DATE.year + 1):
        deterministic_rate = Decimal("0.0018") + deterministic_decimal(
            "operational_loss",
            year,
            min_value=Decimal("0"),
            max_value=Decimal("0.0016"),
        )
        stress_addon = Decimal("0.0010") if year in {2020, 2022} else Decimal("0")
        rows.append(
            OperationalRiskLossInput(
                portfolio_id=CAPITAL_PORTFOLIO_ID,
                year=year,
                annual_operational_loss=q2(base_bi * (deterministic_rate + stress_addon)),
                loss_data_quality_met=True,
                source=PREPARED_CAPITAL_SOURCE,
            )
        )
    return rows


def build_cva_portfolio_inputs(context: GenerationContext) -> list[CvaPortfolioInput]:
    """Generate prepared portfolio-level CVA parameters."""
    cva_ead = sum((row.ead for row in build_cva_netting_sets(context)), Decimal("0"))
    return [
        CvaPortfolioInput(
            portfolio_id=CAPITAL_PORTFOLIO_ID,
            calculation_date=AS_OF_DATE,
            approach="BA_FULL",
            aggregate_non_centrally_cleared_derivative_notional=q2(cva_ead * Decimal("10")),
            ccr_capital_requirement=q2(cva_ead * Decimal("0.08")),
            materiality_option_elected=False,
            supervisor_approved_sa_cva=False,
            alpha=Decimal("1.40"),
            rho=Decimal("0.50"),
            beta=Decimal("0.25"),
            sa_cva_multiplier=Decimal("1.25"),
            source=PREPARED_CAPITAL_SOURCE,
        )
    ]


def build_cva_netting_sets(context: GenerationContext) -> list[CvaNettingSetInput]:
    """Generate prepared BA-CVA netting-set rows from BANK/FI portfolio exposures."""
    grouped: dict[str, dict[str, Decimal]] = {}
    for row in context.core_rows:
        if row["entity_class"] not in {"BANK", "FI"}:
            continue
        counterparty = str(row["counterparty_gid"])
        exposure = Decimal(row["exposure_amount"])
        maturity = Decimal(row["residual_maturity"])
        bucket = grouped.setdefault(
            counterparty,
            {"exposure": Decimal("0"), "weighted_maturity": Decimal("0"), "count": Decimal("0")},
        )
        bucket["exposure"] += exposure
        bucket["weighted_maturity"] += exposure * maturity
        bucket["count"] += Decimal("1")

    rows: list[CvaNettingSetInput] = []
    ranked = sorted(grouped.items(), key=lambda item: item[1]["exposure"], reverse=True)[:12]
    for counterparty, values in ranked:
        exposure = values["exposure"]
        if exposure <= Decimal("0"):
            continue
        maturity = values["weighted_maturity"] / exposure
        effective_maturity = min(max(maturity, Decimal("1")), Decimal("5"))
        discount_factor = Decimal("1") / (Decimal("1") + Decimal("0.025") * effective_maturity)
        risk_weight = Decimal("0.045") + deterministic_decimal(
            "cva_rw",
            counterparty,
            min_value=Decimal("0"),
            max_value=Decimal("0.035"),
        )
        rows.append(
            CvaNettingSetInput(
                portfolio_id=CAPITAL_PORTFOLIO_ID,
                counterparty_id=counterparty,
                ead=q2(exposure * Decimal("0.050")),
                maturity_years=q4(effective_maturity),
                risk_weight=q4(risk_weight),
                discount_factor=q6(discount_factor),
            )
        )
    return rows


def build_cva_hedges(context: GenerationContext) -> list[CvaHedgeInput]:
    """Generate prepared eligible hedge rows linked to the largest CVA netting sets."""
    netting_sets = build_cva_netting_sets(context)[:3]
    rows: list[CvaHedgeInput] = []
    for index, netting_set in enumerate(netting_sets, start=1):
        rows.append(
            CvaHedgeInput(
                portfolio_id=CAPITAL_PORTFOLIO_ID,
                hedge_id=f"CVA_HEDGE_{index:02d}_{netting_set.counterparty_id}",
                effective_notional=q2(netting_set.ead * Decimal("0.18")),
                risk_weight=netting_set.risk_weight,
                eligible=True,
            )
        )
    return rows


def build_leverage_exposures(context: GenerationContext) -> list[LeverageExposureInput]:
    """Generate prepared leverage exposure measure component rows."""
    total_exposure = portfolio_exposure(context)
    derivative_ead = derivative_exposure_base(context)
    sft_gross = bank_fi_exposure(context) * Decimal("0.030")
    return [
        LeverageExposureInput(
            portfolio_id=CAPITAL_PORTFOLIO_ID,
            calculation_date=AS_OF_DATE,
            on_balance_sheet_exposures=q2(total_exposure),
            derivative_replacement_cost=q2(derivative_ead * Decimal("0.20")),
            derivative_potential_future_exposure=q2(derivative_ead * Decimal("0.80")),
            sft_gross_exposure=q2(sft_gross),
            sft_netting_benefit=q2(sft_gross * Decimal("0.35")),
            tier1_deductions_eligible_for_exposure_measure=q2(total_exposure * Decimal("0.002")),
            source=PREPARED_CAPITAL_SOURCE,
        )
    ]


def build_leverage_off_balance_sheet_items(
    context: GenerationContext,
) -> list[LeverageOffBalanceSheetItemInput]:
    """Generate prepared off-balance sheet items for leverage ratio calculations."""
    exposure_by_class: dict[str, Decimal] = {}
    exposure_by_sub_class: dict[str, Decimal] = {}
    for row in context.core_rows:
        exposure = Decimal(row["exposure_amount"])
        exposure_by_class[row["entity_class"]] = (
            exposure_by_class.get(row["entity_class"], Decimal("0")) + exposure
        )
        exposure_by_sub_class[row["sub_class"]] = (
            exposure_by_sub_class.get(row["sub_class"], Decimal("0")) + exposure
        )

    trade_finance = sum(
        (
            exposure_by_sub_class.get(sub_class, Decimal("0"))
            for sub_class in {"OBJECT_FINANCE", "COMMODITIES_FINANCE", "PROJECT_FINANCE"}
        ),
        Decimal("0"),
    )
    return [
        LeverageOffBalanceSheetItemInput(
            portfolio_id=CAPITAL_PORTFOLIO_ID,
            item_id="UNDRAWN_CORPORATE_COMMITMENTS",
            notional=q2(exposure_by_class.get("CORP", Decimal("0")) * Decimal("0.12")),
            credit_conversion_factor=Decimal("0.40"),
        ),
        LeverageOffBalanceSheetItemInput(
            portfolio_id=CAPITAL_PORTFOLIO_ID,
            item_id="UNDRAWN_RETAIL_COMMITMENTS",
            notional=q2(exposure_by_class.get("RETAIL", Decimal("0")) * Decimal("0.08")),
            credit_conversion_factor=Decimal("0.10"),
        ),
        LeverageOffBalanceSheetItemInput(
            portfolio_id=CAPITAL_PORTFOLIO_ID,
            item_id="TRADE_FINANCE_OFF_BALANCE",
            notional=q2(trade_finance * Decimal("0.10")),
            credit_conversion_factor=Decimal("0.20"),
        ),
    ]


def validate_generated_package(file_rows: dict[str, list[Any]], context: GenerationContext) -> None:
    """Run cross-file validation gates required by the executive plan."""
    required = set(GENERATED_FILE_ORDER)
    if set(file_rows) != required:
        raise ValueError(f"missing generated files: {sorted(required - set(file_rows))}")

    scenario_set = {row.scenario_id for row in file_rows["scenario_definitions.csv"]}
    projection_dates = {row.projection_date for row in file_rows["forecast_calendar.csv"]}
    asset_ids = {row["id"] for row in context.core_rows}
    allowed_overlays = {"EU_CRR3_EBA", "UK_PRA_BASEL_3_1", "CH_FINMA_BASEL_III_FINAL"}

    for file_name, rows in file_rows.items():
        if not rows:
            raise ValueError(f"{file_name} has no rows")

    for file_name, rows in file_rows.items():
        for row in rows:
            row_scenario = getattr(row, "scenario_id", None)
            if row_scenario is not None and row_scenario not in scenario_set:
                raise ValueError(f"{file_name} references unknown scenario {row_scenario}")
            row_date = getattr(row, "projection_date", None)
            if row_date is not None and row_date not in projection_dates:
                raise ValueError(f"{file_name} references unknown projection date {row_date}")

    for row in file_rows["regulatory_overlay_selection.csv"]:
        if row.jurisdiction_overlay not in allowed_overlays:
            raise ValueError(f"unknown regulatory overlay: {row.jurisdiction_overlay}")

    for row in file_rows["profitability_inputs.csv"]:
        if row.id not in asset_ids:
            raise ValueError(f"profitability row references unknown asset {row.id}")

    for row in file_rows["data_quality_flags.csv"]:
        if row.id not in asset_ids:
            raise ValueError(f"quality flag references unknown asset {row.id}")

    capital_portfolios = {CAPITAL_PORTFOLIO_ID}
    for file_name in (
        "capital_positions.csv",
        "operational_risk_business_indicators.csv",
        "operational_risk_losses.csv",
        "cva_portfolio_inputs.csv",
        "cva_netting_sets.csv",
        "cva_hedges.csv",
        "leverage_exposures.csv",
        "leverage_off_balance_sheet_items.csv",
    ):
        for row in file_rows[file_name]:
            if row.portfolio_id not in capital_portfolios:
                raise ValueError(f"{file_name} references unknown portfolio {row.portfolio_id}")

    if len(file_rows["operational_risk_business_indicators.csv"]) < 3:
        raise ValueError("operational risk requires at least three BI years")
    if len(file_rows["operational_risk_losses.csv"]) < 10:
        raise ValueError("operational risk requires ten prepared loss years")
    if not file_rows["cva_netting_sets.csv"]:
        raise ValueError("CVA requires prepared netting-set rows")
    if not file_rows["leverage_off_balance_sheet_items.csv"]:
        raise ValueError("leverage ratio requires prepared off-balance sheet rows")

    migration_totals: dict[tuple[str, int, str, str], Decimal] = {}
    for row in file_rows["rating_migration_matrix.csv"]:
        key = (row.scenario_id, row.projection_year, row.entity_class, row.from_rating)
        migration_totals[key] = migration_totals.get(key, Decimal("0")) + row.migration_probability
    for key, total in migration_totals.items():
        if total != Decimal("1.000000"):
            raise ValueError(f"migration probabilities for {key} sum to {total}")


def write_csv(path: Path, rows: list[Any]) -> None:
    """Write Pydantic rows to CSV with stable headers and scalar formatting."""
    first = rows[0].model_dump(mode="python")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(first))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: csv_value(value) for key, value in row.model_dump(mode="python").items()}
            )


def build_validation_report(file_rows: dict[str, list[Any]]) -> dict[str, Any]:
    """Create a compact machine-readable validation report for the generated package."""
    return {
        "validation_status": "PASSED",
        "validated_on": AS_OF_DATE.isoformat(),
        "quality_gates": [
            "all_expected_files_present",
            "all_rows_pydantic_validated",
            "scenario_references_consistent",
            "projection_dates_consistent",
            "rating_migration_probabilities_sum_to_one",
            "fx_rates_positive",
            "asset_references_consistent",
            "capital_inputs_present",
            "operational_loss_history_present",
            "cva_netting_sets_present",
            "leverage_components_present",
        ],
        "row_counts": {file_name: len(rows) for file_name, rows in file_rows.items()},
    }


def build_readme() -> str:
    """Return README content explaining generated-input purpose and regeneration."""
    return f"""# RWA Steering Generated Missing Inputs

This directory contains generated, non-production inputs for the RWA Steering PoC.
The package is deterministic from seed `{RANDOM_SEED}` and version `{VERSION_ID}`.

These files fill the steering gaps that do not belong inside the RWA calculator:
scenario definitions, forecast calendar, rating migration, DLGD shocks, FX rates,
macro regimes, regulatory overlay selection, profitability proxies, action
constraints, strategy limits, data quality flags and prepared capital-stack
inputs for CVA, operational risk, leverage ratio and capital numerators.

Regenerate with:

```bash
uv run rwa-generate-missing-inputs
```

The data is suitable for hackathon demos and automated tests only. It must not be
presented as production customer data, calibrated market forecasts or approved
regulatory reference data.
"""


def scenario_ids() -> tuple[str, ...]:
    """Return seed scenarios in stable output order."""
    return ("BASE", "DOWNSIDE", "STRESS", "RECOVERY")


def base_growth(scenario: str, entity_class: str) -> Decimal:
    """Return base segment growth before deterministic idiosyncratic noise."""
    by_entity = {
        "SOV": Decimal("0.000"),
        "PSE": Decimal("0.005"),
        "MDB": Decimal("0.005"),
        "BANK": Decimal("0.010"),
        "FI": Decimal("0.012"),
        "CORP": Decimal("0.030"),
        "RETAIL": Decimal("0.025"),
        "OTHER": Decimal("0.010"),
    }
    scenario_shift = {
        "BASE": Decimal("0.000"),
        "DOWNSIDE": Decimal("-0.025"),
        "STRESS": Decimal("-0.070"),
        "RECOVERY": Decimal("0.015"),
    }[scenario]
    return by_entity.get(entity_class, Decimal("0.010")) + scenario_shift


def renewal_rate(scenario: str, entity_class: str) -> Decimal:
    """Return segment renewal assumption based on scenario and counterparty class."""
    base = Decimal("0.920") if entity_class in {"CORP", "RETAIL"} else Decimal("0.960")
    return {
        "BASE": base,
        "DOWNSIDE": base - Decimal("0.080"),
        "STRESS": base - Decimal("0.180"),
        "RECOVERY": min(Decimal("0.990"), base + Decimal("0.030")),
    }[scenario]


def migration_distribution(
    rating_scale: list[str], scenario: str, entity_class: str, from_rating: str
) -> dict[str, Decimal]:
    """Build one clipped and quantized rating transition distribution."""
    idx = rating_scale.index(from_rating)
    if scenario == "BASE":
        shifts = {
            0: Decimal("0.880000"),
            -1: Decimal("0.050000"),
            1: Decimal("0.060000"),
            2: Decimal("0.010000"),
        }
    elif scenario == "DOWNSIDE":
        shifts = {
            0: Decimal("0.750000"),
            -1: Decimal("0.020000"),
            1: Decimal("0.160000"),
            2: Decimal("0.070000"),
        }
    elif scenario == "STRESS":
        severe = entity_class in {"CORP", "BANK", "FI"}
        shifts = (
            {
                0: Decimal("0.620000"),
                1: Decimal("0.230000"),
                2: Decimal("0.120000"),
                3: Decimal("0.030000"),
            }
            if severe
            else {
                0: Decimal("0.700000"),
                1: Decimal("0.200000"),
                2: Decimal("0.080000"),
                3: Decimal("0.020000"),
            }
        )
    else:
        shifts = {
            0: Decimal("0.800000"),
            -1: Decimal("0.120000"),
            -2: Decimal("0.030000"),
            1: Decimal("0.050000"),
        }

    distribution = {rating: Decimal("0.000000") for rating in rating_scale}
    for shift, probability in shifts.items():
        target_idx = min(max(idx + shift, 0), len(rating_scale) - 1)
        distribution[rating_scale[target_idx]] += probability
    return adjust_probability_sum(distribution)


def adjust_probability_sum(distribution: dict[str, Decimal]) -> dict[str, Decimal]:
    """Quantize probabilities and adjust the largest bucket so the row sums to one."""
    quantized = {key: q6(value) for key, value in distribution.items()}
    diff = Decimal("1.000000") - sum(quantized.values(), Decimal("0"))
    if diff != Decimal("0.000000"):
        max_key = max(quantized, key=lambda key: quantized[key])
        quantized[max_key] += diff
    return quantized


def dlgd_parameters(
    scenario: str, entity_class: str, sub_class: str
) -> tuple[Decimal, Decimal, Decimal]:
    """Return multiplier, additive shock and collateral haircut assumptions."""
    secured = "REAL_ESTATE" in sub_class
    if scenario == "BASE":
        return Decimal("1.000"), Decimal("0.000"), Decimal("1.000")
    if scenario == "DOWNSIDE":
        return Decimal("1.080"), Decimal("0.015"), Decimal("1.080") if secured else Decimal("1.050")
    if scenario == "STRESS":
        return Decimal("1.250"), Decimal("0.050"), Decimal("1.220") if secured else Decimal("1.120")
    return Decimal("0.970"), Decimal("0.000"), Decimal("0.980")


def fx_shock(scenario: str, currency: str) -> Decimal:
    """Return deterministic synthetic shock versus EUR reporting currency."""
    shocks = {
        "BASE": {
            "EUR": "0.000",
            "USD": "0.010",
            "GBP": "0.010",
            "CHF": "0.005",
            "PLN": "0.005",
            "SEK": "0.005",
        },
        "DOWNSIDE": {
            "EUR": "0.000",
            "USD": "0.040",
            "GBP": "0.030",
            "CHF": "0.020",
            "PLN": "0.035",
            "SEK": "0.025",
        },
        "STRESS": {
            "EUR": "0.000",
            "USD": "0.080",
            "GBP": "0.040",
            "CHF": "0.060",
            "PLN": "0.050",
            "SEK": "0.040",
        },
        "RECOVERY": {
            "EUR": "0.000",
            "USD": "-0.010",
            "GBP": "-0.010",
            "CHF": "-0.005",
            "PLN": "-0.005",
            "SEK": "-0.005",
        },
    }
    return Decimal(shocks[scenario].get(currency, "0.000"))


def macro_values(
    scenario: str, year_step: Decimal
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Return synthetic macro factors for one scenario and projection year."""
    if scenario == "BASE":
        return (
            Decimal("18") + year_step,
            Decimal("115") + year_step * 5,
            Decimal("70") - year_step * 3,
            Decimal("0.78"),
            Decimal("0.055"),
            Decimal("0.018"),
        )
    if scenario == "DOWNSIDE":
        return (
            Decimal("27") + year_step * 2,
            Decimal("220") + year_step * 12,
            Decimal("-15") - year_step * 4,
            Decimal("0.58"),
            Decimal("0.070") + year_step * Decimal("0.003"),
            Decimal("-0.005"),
        )
    if scenario == "STRESS":
        return (
            Decimal("38") + year_step * 3,
            Decimal("340") + year_step * 18,
            Decimal("-55") - year_step * 5,
            Decimal("0.36"),
            Decimal("0.092") + year_step * Decimal("0.005"),
            Decimal("-0.026"),
        )
    return (
        Decimal("16") - year_step,
        Decimal("95") - year_step * 4,
        Decimal("85") + year_step * 2,
        Decimal("0.84"),
        Decimal("0.052") - year_step * Decimal("0.001"),
        Decimal("0.027"),
    )


def regime_label(spread: Decimal, volatility: Decimal, slope: Decimal, scenario: str) -> str:
    """Classify deterministic macro factors into a regime label."""
    if scenario == "RECOVERY":
        return "RECOVERY"
    if spread > Decimal("250") and volatility > Decimal("30"):
        return "CREDIT_STRESS"
    if slope < Decimal("0"):
        return "LATE_CYCLE"
    if volatility < Decimal("17"):
        return "LOW_VOL_GROWTH"
    return "NORMAL"


def regime_score(scenario: str) -> Decimal:
    """Return scenario-level regime score used by downstream steering."""
    return {
        "BASE": Decimal("0.3000"),
        "DOWNSIDE": Decimal("0.6000"),
        "STRESS": Decimal("0.9000"),
        "RECOVERY": Decimal("0.2000"),
    }[scenario]


def action_allowed(entity_class: str, sub_class: str, action: str) -> bool:
    """Return whether an action is credible for the segment in the demo."""
    if entity_class in {"SOV", "MDB", "PSE"} and action in {"REPRICE", "COLLATERAL_ENHANCEMENT"}:
        return False
    if entity_class == "RETAIL" and action == "SELL_DOWN":
        return False
    if action == "COLLATERAL_ENHANCEMENT" and sub_class in {"SOVEREIGN", "BANK"}:
        return False
    return not (action == "NON_RENEWAL" and entity_class in {"SOV", "MDB"})


def max_reduction(entity_class: str, rating_band: str, action: str, allowed: bool) -> Decimal:
    """Return maximum synthetic exposure reduction for an action rule."""
    if not allowed:
        return Decimal("0")
    base = Decimal("0.10") if entity_class in {"SOV", "MDB"} else Decimal("0.25")
    if rating_band == "HIGH_YIELD":
        base += Decimal("0.10")
    if action == "SELL_DOWN":
        base += Decimal("0.15")
    if action == "REPRICE":
        base = min(base, Decimal("0.10"))
    return min(base, Decimal("0.60"))


def notice_months(action: str, entity_class: str) -> int:
    """Return indicative implementation notice period."""
    if action == "SELL_DOWN":
        return 1
    if action == "NON_RENEWAL":
        return 6 if entity_class == "CORP" else 3
    if action == "COLLATERAL_ENHANCEMENT":
        return 4
    return 2


def complexity(action: str, entity_class: str) -> int:
    """Return action implementation complexity on a one-to-five scale."""
    base = {
        "REDUCE_EXPOSURE": 2,
        "REPRICE": 3,
        "COLLATERAL_ENHANCEMENT": 4,
        "NON_RENEWAL": 3,
        "SELL_DOWN": 4,
    }[action]
    if entity_class in {"SOV", "MDB"}:
        base += 1
    return min(base, 5)


def business_cost_factor(action: str, rating_band: str) -> Decimal:
    """Return business cost factor for ranking steering actions."""
    base = {
        "REDUCE_EXPOSURE": Decimal("0.010"),
        "REPRICE": Decimal("0.006"),
        "COLLATERAL_ENHANCEMENT": Decimal("0.004"),
        "NON_RENEWAL": Decimal("0.015"),
        "SELL_DOWN": Decimal("0.020"),
    }[action]
    if rating_band == "INVESTMENT_GRADE":
        base += Decimal("0.004")
    return base


def max_rwa_growth(scenario: str, entity_class: str) -> Decimal:
    """Return RWA growth guardrail by scenario and class."""
    base = Decimal("0.080") if entity_class in {"CORP", "BANK", "FI"} else Decimal("0.050")
    return {
        "BASE": base,
        "DOWNSIDE": base + Decimal("0.050"),
        "STRESS": base + Decimal("0.100"),
        "RECOVERY": base - Decimal("0.020"),
    }[scenario]


def max_exposure_growth(scenario: str, entity_class: str) -> Decimal:
    """Return exposure growth guardrail by scenario and class."""
    base = Decimal("0.060") if entity_class in {"CORP", "RETAIL"} else Decimal("0.030")
    return {
        "BASE": base,
        "DOWNSIDE": Decimal("0.020"),
        "STRESS": Decimal("-0.020"),
        "RECOVERY": base + Decimal("0.030"),
    }[scenario]


def min_raroc(scenario: str, entity_class: str) -> Decimal:
    """Return minimum RAROC threshold for strategy limits."""
    base = Decimal("0.100") if entity_class in {"CORP", "BANK", "FI"} else Decimal("0.070")
    if scenario == "STRESS":
        return base + Decimal("0.030")
    if scenario == "RECOVERY":
        return base - Decimal("0.010")
    return base


def target_rwa_density(entity_class: str, sub_class: str) -> Decimal:
    """Return target RWA density used for segment breach messaging."""
    if entity_class in {"SOV", "MDB", "PSE"}:
        return Decimal("0.150")
    if entity_class in {"BANK", "FI"}:
        return Decimal("0.450")
    if "REAL_ESTATE" in sub_class:
        return Decimal("0.500")
    if entity_class == "RETAIL":
        return Decimal("0.650")
    return Decimal("0.750")


def portfolio_exposure(context: GenerationContext) -> Decimal:
    """Return total exposure from prepared core rows."""
    return sum((Decimal(row["exposure_amount"]) for row in context.core_rows), Decimal("0"))


def bank_fi_exposure(context: GenerationContext) -> Decimal:
    """Return total BANK/FI exposure used to prepare derivative and SFT inputs."""
    return sum(
        (
            Decimal(row["exposure_amount"])
            for row in context.core_rows
            if row["entity_class"] in {"BANK", "FI"}
        ),
        Decimal("0"),
    )


def derivative_exposure_base(context: GenerationContext) -> Decimal:
    """Return prepared derivative EAD base from BANK/FI exposures."""
    return bank_fi_exposure(context) * Decimal("0.050")


def portfolio_rwa(context: GenerationContext, field_name: str) -> Decimal:
    """Return portfolio RWA from calculator results for one output field."""
    return sum(
        (Decimal(str(result[field_name])) for result in context.calculator_results.values()),
        Decimal("0"),
    )


def maybe_add_quality_flag(
    flags: list[DataQualityFlag],
    seen: set[tuple[str, str, str]],
    row_id: str,
    field_name: str,
    issue_code: str,
    severity: int,
    blocking: bool,
    recommended_fix: str,
    condition: bool,
) -> None:
    """Append one quality flag if its condition is true and it is not duplicated."""
    key = (row_id, field_name, issue_code)
    if condition and key not in seen:
        seen.add(key)
        flags.append(
            DataQualityFlag(
                id=row_id,
                field_name=field_name,
                quality_issue_code=issue_code,
                severity=severity,
                is_blocking=blocking,
                recommended_fix=recommended_fix,
            )
        )


def deterministic_int(*parts: object, minimum: int, maximum: int) -> int:
    """Return a deterministic integer in `[minimum, maximum]` from seed and parts."""
    value = int(digest_hex(*parts)[:12], 16)
    return minimum + value % (maximum - minimum + 1)


def deterministic_decimal(
    *parts: object,
    min_value: Decimal = Decimal("-0.010"),
    max_value: Decimal = Decimal("0.010"),
) -> Decimal:
    """Return a deterministic Decimal in the requested range from seed and parts."""
    value = Decimal(int(digest_hex(*parts)[:12], 16)) / Decimal(16**12 - 1)
    return min_value + (max_value - min_value) * value


def digest_hex(*parts: object) -> str:
    """Hash seed and parts into a stable hex digest for deterministic variation."""
    text = "|".join([str(RANDOM_SEED), *(str(part) for part in parts)])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def csv_value(value: Any) -> Any:
    """Convert Python values to CSV-friendly scalar strings."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def sha256_file(path: Path) -> str:
    """Return SHA-256 hex digest for a generated file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_repo_path(path: str | Path) -> str:
    """Return a portable repository-relative path for manifests."""
    resolved = Path(path).resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def q2(value: Decimal) -> Decimal:
    """Quantize money and bps style values to two decimal places."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def q4(value: Decimal) -> Decimal:
    """Quantize scenario rates to four decimal places."""
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def q6(value: Decimal) -> Decimal:
    """Quantize probabilities and FX rates to six decimal places."""
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def main() -> None:
    """Console entry point for regenerating steering missing inputs."""
    parser = argparse.ArgumentParser(description="Generate synthetic RWA steering missing inputs")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args()

    manifest = generate_missing_inputs(args.output_root)
    print(
        f"Generated {len(manifest.generated_files)} files in {args.output_root} "
        f"with validation_status={manifest.validation_status}"
    )


if __name__ == "__main__":
    main()
