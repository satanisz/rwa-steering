from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from rwa_calculator.paths import PREPROD_CORE_INFO_PATH
from rwa_calculator.rwa_calculator.calculator import RwaCalculator, load_core_csv
from rwa_projection_service.engine import RwaProjectionService
from rwa_projection_service.schemas import ProjectionRequest
from rwa_steering.engine import RwaSteeringPocService
from rwa_steering.input_package import load_steering_input_package
from rwa_steering.schemas import SteeringRequest

RWA_FINAL_FIELD = "basel_3_1_rwa_final"
RWA_FOUNDATION_FIELD = "basel_3_1_rwa_foundation"
RWA_STANDARDISED_FIELD = "basel_3_1_rwa_standardised"
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
class ProjectionDashboardData:
    """Monthly f(x, t) projection output prepared for charts and drill-down tables."""

    as_of_date: date
    projected_months: int
    selected_asset_count: int
    summary: dict[str, Any]
    aggregate: pd.DataFrame
    details: pd.DataFrame
    errors: pd.DataFrame


@dataclass(frozen=True)
class SteeringDashboardData:
    """Scenario steering output prepared for scenario, attribution and action views."""

    as_of_date: date
    projection_dates: list[date]
    selected_asset_count: int
    summaries: pd.DataFrame
    projections: pd.DataFrame
    attributions: pd.DataFrame
    recommendations: pd.DataFrame
    limitations: list[str]
    package_version: str | None
    package_status: str | None


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
    """Load the synthetic pre-prod portfolio rows used by all demo services."""
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


def monthly_projection(
    as_of_date: date,
    projected_months: int = 24,
    top_n_assets: int = 100,
) -> ProjectionDashboardData:
    """Run the monthly projection service for the highest current-RWA assets.

    The projection service treats the calculator as ``f(x, t)``. It advances residual maturity
    at each month-end and calls the calculator again, so the displayed path remains tied to the
    same regulatory engine as the current RWA view.
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
    return ProjectionDashboardData(
        as_of_date=as_of_date,
        projected_months=projected_months,
        selected_asset_count=len(selected_rows),
        summary=response.summary.model_dump(mode="python"),
        aggregate=_projection_aggregate_frame(details),
        details=details,
        errors=pd.DataFrame([error.model_dump(mode="python") for error in response.errors]),
    )


def steering_simulation(
    as_of_date: date,
    scenarios: list[str],
    top_n_assets: int = 75,
    top_n_recommendations: int = 10,
) -> SteeringDashboardData:
    """Run generated-input steering scenarios for a selected RWA-heavy portfolio slice.

    The steering service consumes the generated missing inputs, projects calculator inputs under
    scenario assumptions, re-runs ``rwa_calculator`` and returns summaries, attribution and
    recommendations. The dashboard keeps the asset count bounded so interactive reruns stay fast.
    """
    package = load_steering_input_package()
    projection_dates = [
        row.projection_date
        for row in sorted(package.forecast_calendar, key=lambda item: item.projection_date)
        if row.projection_date >= as_of_date
    ]
    if not projection_dates:
        raise ValueError("No generated projection dates are on or after the selected as-of date.")

    source_rows = load_portfolio_rows()
    selected_rows = select_top_rwa_rows(
        current_rwa_snapshot(as_of_date).results,
        source_rows,
        top_n_assets,
    )
    response = RwaSteeringPocService(input_package=package).run(
        SteeringRequest(
            as_of_date=as_of_date,
            projection_dates=projection_dates,
            scenarios=scenarios,
            core_info=selected_rows,
            top_n_recommendations=top_n_recommendations,
        )
    )
    return SteeringDashboardData(
        as_of_date=as_of_date,
        projection_dates=projection_dates,
        selected_asset_count=len(selected_rows),
        summaries=_models_frame(response.summaries),
        projections=_models_frame(response.projections),
        attributions=_models_frame(response.attributions),
        recommendations=_models_frame(response.recommendations),
        limitations=response.limitations,
        package_version=response.input_package_version,
        package_status=response.input_package_validation_status,
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
    _coerce_numeric_columns(frame, ("exposure_amount", "residual_maturity"))
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


def _models_frame(models: list[Any]) -> pd.DataFrame:
    """Convert Pydantic response models to a chart-friendly DataFrame."""
    frame = pd.DataFrame([model.model_dump(mode="python") for model in models])
    if frame.empty:
        return frame
    for column in frame.columns:
        if "date" in column:
            frame[column] = pd.to_datetime(frame[column])
        elif frame[column].map(lambda value: isinstance(value, Decimal)).any():
            frame[column] = frame[column].map(_decimal_to_float)
    return frame


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
