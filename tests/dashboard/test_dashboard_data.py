from __future__ import annotations

from datetime import date

from rwa_dashboard.data import (
    RWA_FINAL_FIELD,
    available_projection_dates,
    current_rwa_snapshot,
    forecast_projection,
    input_package_overview,
    monte_carlo_forecast,
    rats_optimization,
    regulatory_capital_snapshot,
    runoff_projection,
    steering_simulation,
)
from rwa_dashboard.streamlit_app import (
    CALCULATOR_MATURITY_LABEL,
    CALCULATOR_POSITIONING_DETAILS,
    CALCULATOR_POSITIONING_NOTE,
    LEGACY_METHODOLOGY_LABEL,
    STEERING_MODEL_OPTIONS,
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


def test_monte_carlo_forecast_dashboard_data_exposes_selected_path() -> None:
    forecast = monte_carlo_forecast(
        as_of_date=date(2026, 5, 15),
        scenario_id="BASE",
        model_type="VAR",
        horizon_months=2,
        path_count=2,
        top_n_assets=3,
        random_seed=17,
    )

    assert forecast.summary["path_count"] == 2
    assert forecast.summary["selected_path_id"] in {0, 1}
    assert len(forecast.selected_path) == 3
    assert forecast.portfolio_paths["rwa"].ge(0).all()
    assert forecast.package_status == "PASSED"


def test_rats_dashboard_data_exposes_strategy_and_convergence() -> None:
    rats = rats_optimization(
        as_of_date=date(2026, 5, 15),
        projection_date=date(2026, 12, 31),
        scenario_id="BASE",
        top_n_assets=4,
        top_n_candidates=6,
        max_strategy_legs=2,
        particles=4,
        iterations=3,
        random_seed=19,
    )

    assert rats.summary["projected_rwa_before_strategy"] >= rats.summary["optimized_projected_rwa"]
    assert rats.summary["selected_legs"] <= 2
    assert not rats.convergence.empty
    assert rats.package_status == "PASSED"


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
    assert any("prepared generated CSV" in note for note in capital.methodology_notes)


def test_dashboard_frontend_exposes_all_steering_model_options() -> None:
    assert STEERING_MODEL_OPTIONS == (
        "Run-off f(x,t)",
        "Forecast scenarios",
        "Forecast Monte Carlo",
        "Scenario steering",
        "RATS optimizer",
    )


def test_dashboard_frontend_labels_calculator_maturity_scope() -> None:
    assert CALCULATOR_MATURITY_LABEL == "Proxy calculator"
    assert LEGACY_METHODOLOGY_LABEL == "Run-off f(x,t)"
    assert "legacy scope is limited to Run-off f(x,t)" in CALCULATOR_POSITIONING_NOTE
    assert "not a full regulatory-grade RWA engine" in CALCULATOR_POSITIONING_NOTE
    assert any(
        "prepared pre-prod input data" in detail for detail in CALCULATOR_POSITIONING_DETAILS
    )
    assert any("Run-off f(x,t) only" in detail for detail in CALCULATOR_POSITIONING_DETAILS)


def test_input_package_overview_reads_manifest_and_quality_flags() -> None:
    overview = input_package_overview()

    assert overview.manifest["validation_status"] == "PASSED"
    assert not overview.row_counts.empty
    assert not overview.data_quality_summary.empty


def test_available_projection_dates_are_future_dates() -> None:
    dates = available_projection_dates(date(2026, 5, 15))

    assert dates
    assert min(dates) > date(2026, 5, 15)
