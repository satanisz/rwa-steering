from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from rwa_calculator.paths import PREPROD_CORE_INFO_PATH
from rwa_calculator.rwa_calculator.calculator import RwaCalculator, load_core_csv
from rwa_calculator.rwa_calculator.capital import (
    calculate_cva_risk,
    calculate_leverage_ratio,
    calculate_operational_risk,
    calculate_portfolio_capital,
)
from rwa_calculator.rwa_calculator.capital_models import (
    BusinessIndicatorYear,
    CvaHedge,
    CvaNettingSet,
    CvaRiskRequest,
    LeverageRatioRequest,
    OffBalanceSheetItem,
    OperationalRiskRequest,
    PortfolioCapitalRequest,
)
from rwa_projection_service.engine import RwaProjectionService
from rwa_projection_service.schemas import ProjectionRequest
from rwa_steering.input_package import load_steering_input_package

RWA_FINAL_FIELD = "basel_3_1_rwa_final"
RWA_FOUNDATION_FIELD = "basel_3_1_rwa_foundation"
RWA_STANDARDISED_FIELD = "basel_3_1_rwa_standardised"
CAPITAL_PORTFOLIO_ID = "POC_BANKING_BOOK"
RWA_FIELDS = (
    "basel_3_0_rwa",
    RWA_FOUNDATION_FIELD,
    RWA_STANDARDISED_FIELD,
    RWA_FINAL_FIELD,
)
RISK_WEIGHT_FIELDS = (
    "basel_3_0_rw_final",
    "basel_3_1_rw_foundation",
    "basel_3_1_rw_standardised",
    "basel_3_1_rw_final",
)
CORE_METADATA_COLUMNS = (
    "id",
    "entity_class",
    "sub_class",
    "exposure_ccy",
    "incorporation_country",
    "exposure_amount",
    "residual_maturity",
    "counterparty_fcy_internal_rating",
    "counterparty_lcy_internal_rating",
    "counterparty_credit_quality_grade",
    "counterparty_dlgd",
)


@dataclass(frozen=True)
class CurrentRwaSnapshot:
    """Dashboard-ready point-in-time RWA calculation over the pre-prod portfolio."""

    as_of_date: date
    summary: dict[str, Any]
    results: pd.DataFrame
    by_entity: pd.DataFrame
    basel_stack: pd.DataFrame
    top_assets: pd.DataFrame
    errors: pd.DataFrame


@dataclass(frozen=True)
class RunoffProjectionDashboardData:
    """Closed-book monthly projection prepared for run-off charts and drill-down tables."""

    as_of_date: date
    projected_months: int
    selected_asset_count: int
    summary: dict[str, Any]
    aggregate: pd.DataFrame
    details: pd.DataFrame
    errors: pd.DataFrame


@dataclass(frozen=True)
class RegulatoryCapitalDashboardData:
    """Dashboard-ready Basel III final-reform capital stack beyond credit RWA."""

    as_of_date: date
    selected_asset_count: int
    capital_stack: pd.DataFrame
    output_floor: dict[str, Any]
    operational_risk: dict[str, Any]
    cva_risk: dict[str, Any]
    leverage_ratio: dict[str, Any]
    methodology_notes: list[str]


@dataclass(frozen=True)
class InputPackageOverview:
    """Generated-input package metadata for audit and dashboard data-quality panels."""

    manifest: dict[str, Any]
    validation_report: dict[str, Any]
    row_counts: pd.DataFrame
    data_quality_flags: pd.DataFrame
    data_quality_summary: pd.DataFrame


def default_as_of_date() -> date:
    """Return the generated package as-of date used as dashboard default."""
    package = load_steering_input_package()
    return min(row.as_of_date for row in package.forecast_calendar)


def load_portfolio_rows(row_limit: int | None = None) -> list[dict[str, str]]:
    """Load the prepared pre-prod portfolio rows used by dashboard services."""
    rows = load_core_csv(PREPROD_CORE_INFO_PATH)
    return rows[:row_limit] if row_limit is not None else rows


def current_rwa_snapshot(as_of_date: date, row_limit: int | None = None) -> CurrentRwaSnapshot:
    """Calculate current Basel RWA and aggregate it for the dashboard.

    The calculation delegates to ``rwa_calculator`` for every row. This function only joins
    input metadata, converts numeric columns for charts and builds portfolio summaries.
    """
    rows = load_portfolio_rows(row_limit)
    payload = RwaCalculator.from_files().calculate_batch(rows)
    results = _calculator_results_frame(rows, payload["results"])
    summary = _summary_with_totals(payload["summary"], results)
    return CurrentRwaSnapshot(
        as_of_date=as_of_date,
        summary=summary,
        results=results,
        by_entity=_entity_summary_frame(results),
        basel_stack=_basel_stack_frame(results),
        top_assets=_top_assets_frame(results),
        errors=pd.DataFrame(payload["errors"]),
    )


def runoff_projection(
    as_of_date: date,
    projected_months: int = 24,
    top_n_assets: int = 100,
) -> RunoffProjectionDashboardData:
    """Run the closed-book monthly projection service for the highest current-RWA assets.

    The projection service treats the calculator as ``f(x, t)``. It advances residual maturity
    at each month-end and calls the calculator again. It intentionally does not forecast new
    business, ratings, DLGD or FX, so this view should be read as run-off rather than business
    forecast.
    """
    source_rows = load_portfolio_rows()
    selected_rows = select_top_rwa_rows(
        current_rwa_snapshot(as_of_date).results,
        source_rows,
        top_n_assets,
    )
    response = RwaProjectionService().calculate(
        ProjectionRequest(
            run_date=as_of_date,
            projected_months=projected_months,
            core_info=selected_rows,
        )
    )
    details = _projection_frame(response.projections, selected_rows)
    return RunoffProjectionDashboardData(
        as_of_date=as_of_date,
        projected_months=projected_months,
        selected_asset_count=len(selected_rows),
        summary=response.summary.model_dump(mode="python"),
        aggregate=_projection_aggregate_frame(details),
        details=details,
        errors=pd.DataFrame([error.model_dump(mode="python") for error in response.errors]),
    )


def monthly_projection(
    as_of_date: date,
    projected_months: int = 24,
    top_n_assets: int = 100,
) -> RunoffProjectionDashboardData:
    """Backward-compatible wrapper for the renamed run-off projection."""
    return runoff_projection(as_of_date, projected_months, top_n_assets)


def regulatory_capital_snapshot(
    as_of_date: date,
) -> RegulatoryCapitalDashboardData:
    """Calculate portfolio-level CVA, operational risk, output floor and leverage ratio.

    Credit RWA comes from the calculator output. Non-credit capital inputs are loaded from the
    validated generated-input package, so the dashboard uses prepared CSV data rather than
    inline constants.
    """
    package = load_steering_input_package()
    current = current_rwa_snapshot(as_of_date)
    results = current.results
    credit_pre_floor = Decimal(str(results[RWA_FOUNDATION_FIELD].sum()))
    credit_standardised = Decimal(str(results[RWA_STANDARDISED_FIELD].sum()))
    capital_position = package.capital_position_for(CAPITAL_PORTFOLIO_ID, as_of_date)
    cva_portfolio = package.cva_portfolio_for(CAPITAL_PORTFOLIO_ID, as_of_date)
    cva_result = calculate_cva_risk(
        CvaRiskRequest(
            calculation_date=as_of_date,
            approach=cva_portfolio.approach,
            aggregate_non_centrally_cleared_derivative_notional=(
                cva_portfolio.aggregate_non_centrally_cleared_derivative_notional
            ),
            ccr_capital_requirement=cva_portfolio.ccr_capital_requirement,
            materiality_option_elected=cva_portfolio.materiality_option_elected,
            supervisor_approved_sa_cva=cva_portfolio.supervisor_approved_sa_cva,
            netting_sets=[
                CvaNettingSet(
                    counterparty_id=row.counterparty_id,
                    ead=row.ead,
                    maturity_years=row.maturity_years,
                    risk_weight=row.risk_weight,
                    discount_factor=row.discount_factor,
                )
                for row in package.cva_netting_sets_for(CAPITAL_PORTFOLIO_ID)
            ],
            eligible_hedges=[
                CvaHedge(
                    hedge_id=row.hedge_id,
                    effective_notional=row.effective_notional,
                    risk_weight=row.risk_weight,
                    eligible=row.eligible,
                )
                for row in package.cva_hedges_for(CAPITAL_PORTFOLIO_ID)
            ],
            alpha=cva_portfolio.alpha,
            rho=cva_portfolio.rho,
            beta=cva_portfolio.beta,
            sa_cva_multiplier=cva_portfolio.sa_cva_multiplier,
        )
    )
    operational_losses = package.operational_losses_for(CAPITAL_PORTFOLIO_ID)
    operational_result = calculate_operational_risk(
        OperationalRiskRequest(
            calculation_date=as_of_date,
            annual_business_indicators=[
                BusinessIndicatorYear(
                    year=row.year,
                    interest_leases_dividend_component=row.interest_leases_dividend_component,
                    services_component=row.services_component,
                    financial_component=row.financial_component,
                )
                for row in package.operational_business_indicators_for(CAPITAL_PORTFOLIO_ID)
            ],
            annual_operational_losses=[row.annual_operational_loss for row in operational_losses],
            loss_data_quality_met=all(row.loss_data_quality_met for row in operational_losses),
        )
    )
    cva_rwa = Decimal(str(cva_result.cva_rwa))
    operational_rwa = Decimal(str(operational_result.operational_risk_rwa))
    portfolio_result = calculate_portfolio_capital(
        PortfolioCapitalRequest(
            calculation_date=as_of_date,
            credit_rwa_pre_floor=credit_pre_floor,
            credit_rwa_standardised=credit_standardised,
            cva_rwa=cva_rwa,
            operational_rwa=operational_rwa,
            cet1_capital=capital_position.cet1_capital,
            tier1_capital=capital_position.tier1_capital,
            total_capital=capital_position.total_capital,
        )
    )
    leverage_input = package.leverage_exposure_for(CAPITAL_PORTFOLIO_ID, as_of_date)
    leverage_result = calculate_leverage_ratio(
        LeverageRatioRequest(
            calculation_date=as_of_date,
            tier1_capital=capital_position.tier1_capital,
            on_balance_sheet_exposures=leverage_input.on_balance_sheet_exposures,
            derivative_replacement_cost=leverage_input.derivative_replacement_cost,
            derivative_potential_future_exposure=(
                leverage_input.derivative_potential_future_exposure
            ),
            sft_gross_exposure=leverage_input.sft_gross_exposure,
            sft_netting_benefit=leverage_input.sft_netting_benefit,
            off_balance_sheet_items=[
                OffBalanceSheetItem(
                    item_id=row.item_id,
                    notional=row.notional,
                    credit_conversion_factor=row.credit_conversion_factor,
                )
                for row in package.leverage_off_balance_sheet_items_for(CAPITAL_PORTFOLIO_ID)
            ],
            tier1_deductions_eligible_for_exposure_measure=(
                leverage_input.tier1_deductions_eligible_for_exposure_measure
            ),
            gsib_higher_loss_absorbency_requirement=(
                capital_position.gsib_higher_loss_absorbency_requirement
            ),
        )
    )
    capital_stack = pd.DataFrame(
        [
            {"component": "Credit RWA pre-floor", "rwa": float(credit_pre_floor)},
            {"component": "CVA RWA", "rwa": float(cva_rwa)},
            {"component": "Operational risk RWA", "rwa": float(operational_rwa)},
            {
                "component": "Output floor add-on",
                "rwa": float(portfolio_result.output_floor.output_floor_amount),
            },
        ]
    )
    return RegulatoryCapitalDashboardData(
        as_of_date=as_of_date,
        selected_asset_count=len(results),
        capital_stack=capital_stack,
        output_floor=_capital_model_dict(portfolio_result.output_floor),
        operational_risk=_capital_model_dict(operational_result),
        cva_risk=_capital_model_dict(cva_result),
        leverage_ratio=_capital_model_dict(leverage_result),
        methodology_notes=[
            "Credit RWA uses calculator output; output floor is aggregate and date phased.",
            (
                "Operational, CVA, leverage and capital numerator inputs are loaded from "
                "prepared generated CSV files."
            ),
            "Prepared capital inputs are hash-validated by the generated input manifest.",
        ],
    )


def input_package_overview() -> InputPackageOverview:
    """Load generated-input metadata and row-level quality flags for audit panels."""
    package = load_steering_input_package()
    manifest = package.manifest.model_dump(mode="python")
    validation_report = json.loads((package.root / "validation_report.json").read_text())
    row_counts = pd.DataFrame(
        [{"file_name": name, "rows": count} for name, count in manifest["row_counts"].items()]
    )
    flags = pd.DataFrame([row.model_dump(mode="python") for row in package.data_quality_flags])
    if flags.empty:
        summary = pd.DataFrame(columns=["quality_issue_code", "severity", "is_blocking", "count"])
    else:
        summary = (
            flags.groupby(["quality_issue_code", "severity", "is_blocking"], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values(["severity", "count"], ascending=[False, False])
        )
    return InputPackageOverview(
        manifest=manifest,
        validation_report=validation_report,
        row_counts=row_counts,
        data_quality_flags=flags,
        data_quality_summary=summary,
    )


def select_top_rwa_rows(
    current_results: pd.DataFrame,
    source_rows: list[dict[str, str]],
    limit: int,
) -> list[dict[str, str]]:
    """Return source input rows matching the highest current Basel 3.1 final RWA assets."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    ranked_ids = list(current_results.nlargest(limit, RWA_FINAL_FIELD)["id"])
    source_by_id = {row["id"]: row for row in source_rows}
    return [source_by_id[row_id] for row_id in ranked_ids if row_id in source_by_id]


def _calculator_results_frame(
    source_rows: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> pd.DataFrame:
    """Join calculator output with input metadata and convert numeric values for charts."""
    if not results:
        return pd.DataFrame(columns=[*CORE_METADATA_COLUMNS, *RWA_FIELDS])
    metadata = pd.DataFrame(source_rows)[list(CORE_METADATA_COLUMNS)]
    output = pd.DataFrame(results)
    frame = metadata.merge(output, on="id", how="inner")
    _coerce_numeric_columns(frame, ("exposure_amount", "residual_maturity", "counterparty_dlgd"))
    _coerce_numeric_columns(frame, (*RWA_FIELDS, *RISK_WEIGHT_FIELDS))
    frame["rwa_density"] = _safe_ratio(frame[RWA_FINAL_FIELD], frame["exposure_amount"])
    return frame


def _summary_with_totals(summary: dict[str, Any], results: pd.DataFrame) -> dict[str, Any]:
    """Add portfolio totals to the calculator summary dictionary."""
    enriched = dict(summary)
    total_exposure = float(results["exposure_amount"].sum()) if not results.empty else 0.0
    total_rwa = float(results[RWA_FINAL_FIELD].sum()) if not results.empty else 0.0
    enriched["total_exposure_amount"] = total_exposure
    enriched[RWA_FINAL_FIELD] = total_rwa
    enriched["basel_3_1_rwa_density"] = total_rwa / total_exposure if total_exposure else None
    return enriched


def _entity_summary_frame(results: pd.DataFrame) -> pd.DataFrame:
    """Aggregate current RWA, exposure and density by Basel entity class."""
    if results.empty:
        return pd.DataFrame(
            columns=["entity_class", "asset_count", "exposure_amount", RWA_FINAL_FIELD]
        )
    grouped = (
        results.groupby("entity_class", dropna=False)
        .agg(
            asset_count=("id", "count"),
            exposure_amount=("exposure_amount", "sum"),
            basel_3_0_rwa=("basel_3_0_rwa", "sum"),
            basel_3_1_rwa_foundation=(RWA_FOUNDATION_FIELD, "sum"),
            basel_3_1_rwa_standardised=(RWA_STANDARDISED_FIELD, "sum"),
            basel_3_1_rwa_final=(RWA_FINAL_FIELD, "sum"),
        )
        .reset_index()
        .sort_values(RWA_FINAL_FIELD, ascending=False)
    )
    grouped["rwa_density"] = _safe_ratio(grouped[RWA_FINAL_FIELD], grouped["exposure_amount"])
    return grouped


def _basel_stack_frame(results: pd.DataFrame) -> pd.DataFrame:
    """Build a compact Basel 3.0 versus Basel 3.1 RWA comparison frame."""
    labels = {
        "basel_3_0_rwa": "Basel 3.0 IRB",
        RWA_FOUNDATION_FIELD: "Basel 3.1 foundation",
        RWA_STANDARDISED_FIELD: "Basel 3.1 standardised",
        RWA_FINAL_FIELD: "Basel 3.1 final",
    }
    return pd.DataFrame(
        [{"measure": labels[field], "rwa": float(results[field].sum())} for field in labels]
    )


def _top_assets_frame(results: pd.DataFrame, limit: int = 25) -> pd.DataFrame:
    """Return the largest current-RWA assets for table and selection controls."""
    if results.empty:
        return pd.DataFrame()
    columns = [
        "id",
        "counterparty_gid",
        "entity_class",
        "sub_class",
        "exposure_ccy",
        "exposure_amount",
        RWA_FINAL_FIELD,
        "rwa_density",
        "residual_maturity",
        "counterparty_fcy_internal_rating",
    ]
    return results.nlargest(limit, RWA_FINAL_FIELD)[columns].reset_index(drop=True)


def _projection_frame(projections: list[Any], source_rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert projection models to a metadata-rich DataFrame."""
    if not projections:
        return pd.DataFrame()
    frame = pd.DataFrame([row.model_dump(mode="python") for row in projections])
    metadata = pd.DataFrame(source_rows)[
        ["id", "entity_class", "sub_class", "exposure_ccy", "counterparty_gid"]
    ]
    frame = frame.merge(metadata, on="id", how="left")
    frame["projection_date"] = pd.to_datetime(frame["projection_date"])
    _coerce_numeric_columns(frame, (*RWA_FIELDS, *RISK_WEIGHT_FIELDS))
    return frame


def _projection_aggregate_frame(details: pd.DataFrame) -> pd.DataFrame:
    """Aggregate projection output across all selected assets by projection date."""
    if details.empty:
        return pd.DataFrame(columns=["projection_date", *RWA_FIELDS])
    return (
        details.groupby("projection_date", dropna=False)
        .agg(
            basel_3_0_rwa=("basel_3_0_rwa", "sum"),
            basel_3_1_rwa_foundation=(RWA_FOUNDATION_FIELD, "sum"),
            basel_3_1_rwa_standardised=(RWA_STANDARDISED_FIELD, "sum"),
            basel_3_1_rwa_final=(RWA_FINAL_FIELD, "sum"),
        )
        .reset_index()
        .sort_values("projection_date")
    )


def _capital_model_dict(model: Any) -> dict[str, Any]:
    """Convert nested capital response models to scalar dashboard values."""
    data = model.model_dump(mode="python")
    converted: dict[str, Any] = {}
    for key, value in data.items():
        if key == "trace":
            continue
        if isinstance(value, Decimal):
            converted[key] = float(value)
        elif isinstance(value, date):
            converted[key] = value.isoformat()
        else:
            converted[key] = value
    return converted


def _coerce_numeric_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    """Convert decimal-like columns in-place to floats for plotting libraries."""
    for column in columns:
        if column in frame.columns:
            frame[column] = frame[column].map(_decimal_to_float)


def _decimal_to_float(value: Any) -> float | None:
    """Convert Decimal, string or numeric values to float while preserving blanks."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Return element-wise ``numerator / denominator`` with zero denominators blanked."""
    return numerator.div(denominator.where(denominator != 0))
