from __future__ import annotations

from datetime import date

from rwa_dashboard.data import (
    RWA_FINAL_FIELD,
    current_rwa_snapshot,
    forecast_projection,
    input_package_overview,
    runoff_projection,
    steering_simulation,
)


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


def test_forecast_projection_recalculates_rwa_on_generated_future_inputs() -> None:
    forecast = forecast_projection(
        as_of_date=date(2026, 5, 15),
        scenarios=["BASE", "STRESS"],
        top_n_assets=3,
    )

    assert forecast.selected_asset_count == 3
    assert set(forecast.aggregate["scenario_id"]) == {"BASE", "STRESS"}
    assert set(forecast.details["forecast_stage"]) == {"Actual", "Forecast"}
    assert forecast.aggregate["projected_rwa"].ge(0).all()
    assert {"forecast_exposure_amount", "forecast_rating", "forecast_dlgd"}.issubset(
        forecast.details.columns
    )


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
