from __future__ import annotations

import csv
from decimal import Decimal

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
