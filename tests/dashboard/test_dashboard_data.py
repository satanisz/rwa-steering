from __future__ import annotations

from datetime import date

from rwa_dashboard.data import (
    RWA_FINAL_FIELD,
    current_rwa_snapshot,
    input_package_overview,
    regulatory_capital_snapshot,
    runoff_projection,
)
from rwa_dashboard.streamlit_app import MODEL_RUNOFF


def test_current_rwa_snapshot_aggregates_preprod_rows() -> None:
    snapshot = current_rwa_snapshot(date(2026, 5, 15), row_limit=10)

    assert snapshot.summary["input_data_records"] == 10
    assert snapshot.summary["output_failure_records"] == 0
    assert snapshot.summary[RWA_FINAL_FIELD] > 0
    assert not snapshot.by_entity.empty
    assert snapshot.results[RWA_FINAL_FIELD].ge(0).all()


def test_runoff_projection_exposes_final_rwa_path() -> None:
    projection = runoff_projection(date(2026, 5, 15), projected_months=2, top_n_assets=3)

    assert projection.selected_asset_count == 3
    assert len(projection.aggregate) == 3
    assert RWA_FINAL_FIELD in projection.details.columns
    assert projection.aggregate[RWA_FINAL_FIELD].ge(0).all()


def test_regulatory_capital_dashboard_data_exposes_final_reform_modules() -> None:
    capital = regulatory_capital_snapshot(date(2026, 5, 15))

    assert capital.output_floor["floor_calibration"] == 0.7
    assert capital.output_floor["applicable_rwa"] >= capital.output_floor["pre_floor_rwa"]
    assert capital.operational_risk["operational_risk_rwa"] > 0
    assert capital.cva_risk["approach_used"] == "BA_FULL"
    assert capital.leverage_ratio["exposure_measure"] > 0
    assert {"Credit RWA pre-floor", "CVA RWA", "Operational risk RWA"}.issubset(
        set(capital.capital_stack["component"])
    )
    assert any("prepared generated CSV" in note for note in capital.calculation_notes)


def test_dashboard_frontend_uses_fixed_runoff_workflow() -> None:
    assert MODEL_RUNOFF == "Run-off f(x,t)"


def test_input_package_overview_reads_manifest_and_quality_flags() -> None:
    overview = input_package_overview()

    assert overview.manifest["validation_status"] == "PASSED"
    assert not overview.row_counts.empty
    assert not overview.data_quality_summary.empty
