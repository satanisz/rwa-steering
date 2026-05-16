from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from .schemas import EvidenceItem, EvidenceReference, MetricFact


@dataclass(frozen=True)
class AgentRuntimeContext:
    """In-memory read-only view of calculated dashboard artifacts for an agent run."""

    as_of_date: date
    scenario_id: str
    snapshot: Any
    capital: Any
    overview: Any
    runs: Any


def metric_facts(context: AgentRuntimeContext) -> list[MetricFact]:
    """Extract scalar facts from already calculated dashboard data."""
    output_floor = context.capital.output_floor
    leverage = context.capital.leverage_ratio
    quality_flags = int(context.overview.data_quality_flags.shape[0])
    blocking_flags = _blocking_quality_flags(context.overview.data_quality_summary)
    facts = [
        MetricFact(
            name="current_credit_rwa_final",
            value=_decimal(context.snapshot.summary["basel_3_1_rwa_final"]),
            unit="PLN",
            source="current_rwa_snapshot.summary",
            as_of_date=context.as_of_date,
        ),
        MetricFact(
            name="applicable_total_rwa",
            value=_decimal(output_floor["applicable_rwa"]),
            unit="PLN",
            source="regulatory_capital_snapshot.output_floor",
            as_of_date=context.as_of_date,
        ),
        MetricFact(
            name="cet1_ratio",
            value=_decimal(output_floor["cet1_ratio"]),
            unit="ratio",
            source="regulatory_capital_snapshot.output_floor",
            as_of_date=context.as_of_date,
        ),
        MetricFact(
            name="total_capital_ratio",
            value=_decimal(output_floor["total_capital_ratio"]),
            unit="ratio",
            source="regulatory_capital_snapshot.output_floor",
            as_of_date=context.as_of_date,
        ),
        MetricFact(
            name="leverage_ratio",
            value=_decimal(leverage["leverage_ratio"]),
            unit="ratio",
            source="regulatory_capital_snapshot.leverage_ratio",
            as_of_date=context.as_of_date,
        ),
        MetricFact(
            name="data_quality_findings",
            value=quality_flags,
            unit="count",
            source="input_package_overview.data_quality_flags",
            as_of_date=context.as_of_date,
        ),
        MetricFact(
            name="blocking_data_quality_findings",
            value=blocking_flags,
            unit="count",
            source="input_package_overview.data_quality_summary",
            as_of_date=context.as_of_date,
        ),
        MetricFact(
            name="calculated_model_count",
            value=int(context.runs.model_summary["model"].nunique()),
            unit="count",
            source="model_run_set.model_summary",
            as_of_date=context.as_of_date,
            scenario_id=context.scenario_id,
        ),
        MetricFact(
            name="sector_projection_rows",
            value=int(context.runs.sector_projection.shape[0]),
            unit="rows",
            source="model_run_set.sector_projection",
            as_of_date=context.as_of_date,
            scenario_id=context.scenario_id,
        ),
    ]
    for row in _records(context.runs.model_summary):
        facts.append(
            MetricFact(
                name="model_projected_rwa",
                value=_decimal(row["projected_rwa"]),
                unit="PLN",
                source="model_run_set.model_summary",
                as_of_date=context.as_of_date,
                scenario_id=str(row["scenario_id"]),
                model=str(row["model"]),
                description="Terminal projected RWA by calculated model.",
            )
        )
        facts.append(
            MetricFact(
                name="model_rwa_delta",
                value=_decimal(row["rwa_delta"]),
                unit="PLN",
                source="model_run_set.model_summary",
                as_of_date=context.as_of_date,
                scenario_id=str(row["scenario_id"]),
                model=str(row["model"]),
                description="Terminal projected RWA movement versus model baseline.",
            )
        )
    return facts


def evidence_inventory(context: AgentRuntimeContext) -> list[EvidenceItem]:
    """Build evidence records from prepared files and calculated model frames."""
    manifest = context.overview.manifest
    file_hashes = manifest.get("file_sha256", {})
    row_counts = manifest.get("row_counts", {})
    items: list[EvidenceItem] = [
        EvidenceItem(
            artifact_id="current_rwa_snapshot.results",
            artifact_type="calculated_frame",
            title="Current calculator output",
            source_name="rwa_dashboard.data.current_rwa_snapshot",
            row_count=int(context.snapshot.results.shape[0]),
            summary="Exposure-level Basel RWA values produced by the calculator.",
        ),
        EvidenceItem(
            artifact_id="regulatory_capital_snapshot.capital_stack",
            artifact_type="calculated_frame",
            title="Regulatory capital stack",
            source_name="rwa_dashboard.data.regulatory_capital_snapshot",
            row_count=int(context.capital.capital_stack.shape[0]),
            summary="Credit, CVA, operational risk and output-floor capital components.",
        ),
        EvidenceItem(
            artifact_id="model_run_set.model_summary",
            artifact_type="calculated_frame",
            title="Model run summary",
            source_name="rwa_dashboard.data.model_run_set",
            row_count=int(context.runs.model_summary.shape[0]),
            summary="Terminal projection row for each calculated dashboard model.",
        ),
        EvidenceItem(
            artifact_id="model_run_set.sector_projection",
            artifact_type="calculated_frame",
            title="Sector projection propagation",
            source_name="rwa_dashboard.data.model_run_set",
            row_count=int(context.runs.sector_projection.shape[0]),
            summary="Sector-level projected RWA records exposed by model outputs.",
        ),
        EvidenceItem(
            artifact_id="input_package.validation_report",
            artifact_type="validation_report",
            title="Generated input validation report",
            source_name="validation_report.json",
            row_count=len(context.overview.validation_report.get("quality_gates", [])),
            summary=f"Validation status {manifest['validation_status']}.",
        ),
    ]
    for file_name, sha256 in sorted(file_hashes.items()):
        items.append(
            EvidenceItem(
                artifact_id=f"generated_input.{file_name}",
                artifact_type="prepared_input_file",
                title=file_name,
                source_name=file_name,
                row_count=row_counts.get(file_name),
                sha256=sha256,
                summary="Hash-validated generated input file used by dashboard services.",
            )
        )
    return items


def lineage_records(context: AgentRuntimeContext) -> list[dict[str, str | int]]:
    """Return a compact lineage map from prepared files to dashboard and agent outputs."""
    manifest = context.overview.manifest
    return [
        {
            "source": "Prepared exposure file",
            "target": "RWA calculator",
            "artifact_type": "CSV input",
            "records": int(context.snapshot.summary["input_data_records"]),
            "status": "CALCULATED",
        },
        {
            "source": "Generated input package",
            "target": "Forecast, steering and capital modules",
            "artifact_type": "Generated CSV package",
            "records": len(manifest["generated_files"]),
            "status": str(manifest["validation_status"]),
        },
        {
            "source": "Model run set",
            "target": "Agent graph",
            "artifact_type": "Calculated frames",
            "records": int(context.runs.projection_comparison.shape[0]),
            "status": "READ_ONLY",
        },
        {
            "source": "Agent graph",
            "target": "Dashboard commentary",
            "artifact_type": "Structured briefing",
            "records": 5,
            "status": "GENERATED_FROM_CALCULATED_DATA",
        },
    ]


def evidence_ref(
    source_name: str,
    identifier: str,
    *,
    metric_name: str | None = None,
    row_count: int | None = None,
    sha256: str | None = None,
    source_type: str = "calculated_frame",
) -> EvidenceReference:
    """Create a typed evidence reference for agent findings."""
    return EvidenceReference(
        source_type=source_type,
        source_name=source_name,
        identifier=identifier,
        metric_name=metric_name,
        row_count=row_count,
        sha256=sha256,
    )


def top_model_movements(frame: pd.DataFrame, limit: int = 3) -> list[dict[str, Any]]:
    """Return the largest absolute projected RWA movements from model summary."""
    if frame.empty or "rwa_delta" not in frame.columns:
        return []
    ranked = frame.assign(abs_delta=frame["rwa_delta"].abs()).nlargest(limit, "abs_delta")
    return _records(ranked.drop(columns=["abs_delta"]))


def largest_capital_components(frame: pd.DataFrame, limit: int = 3) -> list[dict[str, Any]]:
    """Return the largest RWA components in the calculated capital stack."""
    if frame.empty or "rwa" not in frame.columns:
        return []
    return _records(frame.nlargest(limit, "rwa"))


def _blocking_quality_flags(summary: pd.DataFrame) -> int:
    if summary.empty or "is_blocking" not in summary.columns:
        return 0
    return int(summary.loc[summary["is_blocking"], "count"].sum())


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return frame.to_dict(orient="records") if not frame.empty else []


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))
