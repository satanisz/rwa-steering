from __future__ import annotations

import csv
from decimal import Decimal

from rwa_calculator.paths import PREPROD_CORE_INFO_PATH
from rwa_calculator.rwa_calculator.calculator import load_core_csv
from rwa_steering.input_package import load_steering_input_package
from rwa_steering.missing_inputs import GENERATED_FILE_ORDER, generate_missing_inputs


def test_missing_inputs_generator_writes_valid_package(tmp_path) -> None:
    """Generated steering inputs should be complete, validated and internally consistent."""
    manifest = generate_missing_inputs(tmp_path)

    assert manifest.validation_status == "PASSED"
    assert manifest.row_counts["scenario_definitions.csv"] == 4
    assert manifest.row_counts["forecast_calendar.csv"] == 6
    assert manifest.row_counts["profitability_inputs.csv"] == 1000
    assert manifest.row_counts["data_quality_flags.csv"] == 120
    for file_name in GENERATED_FILE_ORDER:
        assert (tmp_path / file_name).exists()

    with (tmp_path / "forecast_calendar.csv").open(encoding="utf-8", newline="") as handle:
        dates = {row["projection_date"] for row in csv.DictReader(handle)}
    assert "2026-05-15" in dates
    assert "2030-12-31" in dates


def test_rating_migration_probabilities_sum_to_one(tmp_path) -> None:
    """Every scenario/year/entity/from-rating migration vector must sum to one."""
    generate_missing_inputs(tmp_path)

    totals: dict[tuple[str, str, str, str], Decimal] = {}
    with (tmp_path / "rating_migration_matrix.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (
                row["scenario_id"],
                row["projection_year"],
                row["entity_class"],
                row["from_rating"],
            )
            totals[key] = totals.get(key, Decimal("0")) + Decimal(row["migration_probability"])

    assert totals
    assert set(totals.values()) == {Decimal("1.000000")}


def test_loaded_input_package_projects_rows_from_generated_assumptions() -> None:
    """Runtime package loader should expose generated assumptions to steering code."""
    package = load_steering_input_package()
    row = load_core_csv(PREPROD_CORE_INFO_PATH)[0]

    projected = package.project_row(
        row,
        "STRESS",
        as_of_date=package.forecast_calendar[0].as_of_date,
        projection_date=package.forecast_calendar[2].projection_date,
    )
    scenario = package.scenario_assumption("STRESS", package.forecast_calendar[2].projection_date)

    assert package.manifest.validation_status == "PASSED"
    assert scenario.regime_label == "CREDIT_STRESS"
    assert Decimal(projected["exposure_amount"]) >= Decimal("0")
    assert projected["counterparty_fcy_internal_rating"] != row["counterparty_fcy_internal_rating"]
    assert package.profitability_for(row["id"]) is not None
    assert package.best_reduction_constraint(row) is not None
