from __future__ import annotations

from datetime import date

from rwa_dashboard.data import (
    RWA_FINAL_FIELD,
    current_rwa_snapshot,
    input_package_overview,
    monthly_projection,
    steering_simulation,
)


def test_current_rwa_snapshot_aggregates_preprod_rows() -> None:
    snapshot = current_rwa_snapshot(date(2026, 5, 15), row_limit=10)

    assert snapshot.summary["input_data_records"] == 10
    assert snapshot.summary["output_failure_records"] == 0
    assert snapshot.summary[RWA_FINAL_FIELD] > 0
    assert not snapshot.by_entity.empty
    assert snapshot.results[RWA_FINAL_FIELD].ge(0).all()


def test_monthly_projection_exposes_final_rwa_path() -> None:
    projection = monthly_projection(date(2026, 5, 15), projected_months=2, top_n_assets=3)

    assert projection.selected_asset_count == 3
    assert len(projection.aggregate) == 3
    assert RWA_FINAL_FIELD in projection.details.columns
    assert projection.aggregate[RWA_FINAL_FIELD].ge(0).all()


def test_steering_simulation_uses_generated_inputs_for_scenarios() -> None:
    steering = steering_simulation(
        as_of_date=date(2026, 5, 15),
        scenarios=["BASE", "STRESS"],
        top_n_assets=3,
        top_n_recommendations=2,
    )

    assert set(steering.summaries["scenario_id"]) == {"BASE", "STRESS"}
    assert not steering.attributions.empty
    assert len(steering.recommendations) <= 2
    assert steering.package_status == "PASSED"


def test_input_package_overview_reads_manifest_and_quality_flags() -> None:
    overview = input_package_overview()

    assert overview.manifest["validation_status"] == "PASSED"
    assert not overview.row_counts.empty
    assert not overview.data_quality_summary.empty
