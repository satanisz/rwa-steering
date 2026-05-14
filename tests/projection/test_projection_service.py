from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from itertools import pairwise

import pytest
from fastapi.testclient import TestClient

from rwa_calculator.paths import PREPROD_CORE_INFO_PATH
from rwa_projection_service.engine import RwaProjectionService
from rwa_projection_service.fastapi_app import create_app
from rwa_projection_service.schemas import ProjectionRequest


def load_sample_row() -> dict[str, str]:
    with PREPROD_CORE_INFO_PATH.open(newline="", encoding="utf-8") as handle:
        return next(csv.DictReader(handle))


def test_projection_service_calculates_t0_and_month_end_projection_points() -> None:
    row = load_sample_row()
    request = ProjectionRequest(
        run_date=date(2026, 1, 1),
        projected_months=2,
        core_info=[row],
    )

    response = RwaProjectionService().calculate(request)

    assert response.projection_dates == [
        date(2026, 1, 1),
        date(2026, 1, 31),
        date(2026, 2, 28),
    ]
    assert response.summary.input_data_records == 1
    assert response.summary.output_successful_records == 1
    assert response.summary.output_successful_projection_records == 3
    assert response.summary.output_failure_records == 0
    assert response.results[0]["id"] == row["id"]
    assert response.projections[0].basel_3_1_rwa_final is not None
    assert [projection.projection_date for projection in response.projections] == (
        response.projection_dates
    )


def test_projection_service_returns_two_year_month_end_rwa_path_for_single_asset() -> None:
    row = load_sample_row()
    request = ProjectionRequest(
        run_date=date(2026, 1, 1),
        projected_months=24,
        core_info=[row],
    )

    response = RwaProjectionService().calculate(request)
    rwa_time_series = [
        (projection.projection_date, projection.basel_3_1_rwa_foundation)
        for projection in response.projections
        if projection.id == row["id"]
    ]

    assert response.summary.input_data_records == 1
    assert response.summary.output_successful_records == 1
    assert response.summary.output_successful_projection_records == 25
    assert response.summary.output_failure_records == 0
    assert len(response.projection_dates) == 25
    assert len(rwa_time_series) == 25
    assert rwa_time_series[0][0] == date(2026, 1, 1)
    assert rwa_time_series[1][0] == date(2026, 1, 31)
    assert rwa_time_series[-1][0] == date(2027, 12, 31)
    assert all(rwa is not None and rwa >= Decimal("0") for _, rwa in rwa_time_series)


@pytest.mark.parametrize(
    ("residual_maturity", "expected_first_zero_date"),
    [
        ("1.00", date(2027, 1, 31)),
        ("0.25", date(2026, 4, 30)),
    ],
)
def test_projection_service_returns_declining_rwa_path_after_asset_maturity(
    residual_maturity: str,
    expected_first_zero_date: date,
) -> None:
    row = load_sample_row()
    row["residual_maturity"] = residual_maturity
    row["original_maturity"] = residual_maturity

    response = RwaProjectionService().calculate(
        ProjectionRequest(run_date=date(2026, 1, 1), projected_months=24, core_info=[row])
    )
    rwa_time_series = [
        (projection.projection_date, projection.basel_3_1_rwa_foundation)
        for projection in response.projections
        if projection.id == row["id"]
    ]
    rwa_values = [rwa for _, rwa in rwa_time_series]
    first_zero_index = next(index for index, rwa in enumerate(rwa_values) if rwa == Decimal("0"))

    assert response.summary.output_successful_projection_records == 25
    assert rwa_time_series[0][1] is not None
    assert rwa_time_series[0][1] > Decimal("0")
    assert rwa_time_series[first_zero_index][0] == expected_first_zero_date
    assert all(rwa is not None for rwa in rwa_values)
    assert all(previous >= current for previous, current in pairwise(rwa_values))
    assert all(rwa == Decimal("0") for rwa in rwa_values[first_zero_index:])


def test_projection_service_calculates_maturity_zero_then_projects_zero_after_maturity() -> None:
    row = load_sample_row()
    row["residual_maturity"] = "0"
    row["original_maturity"] = "0"

    response = RwaProjectionService().calculate(
        ProjectionRequest(run_date=date(2026, 1, 1), projected_months=1, core_info=[row])
    )

    assert response.summary.output_successful_records == 1
    assert response.projections[0].projection_date == date(2026, 1, 1)
    assert response.projections[0].basel_3_0_rwa is not None
    assert response.projections[1].projection_date == date(2026, 1, 31)
    assert response.projections[1].basel_3_0_rwa == Decimal("0")
    assert response.projections[1].basel_3_1_rwa_foundation == Decimal("0")
    assert response.projections[1].basel_3_1_rwa_final == Decimal("0")


def test_projection_service_returns_null_projection_values_for_missing_maturity() -> None:
    row = load_sample_row()
    row["residual_maturity"] = ""

    response = RwaProjectionService().calculate(
        ProjectionRequest(run_date=date(2026, 1, 1), projected_months=1, core_info=[row])
    )

    assert response.summary.output_successful_records == 0
    assert response.summary.output_failure_records == 1
    assert response.projections[0].basel_3_0_rwa is None
    assert response.projections[1].basel_3_0_rwa is None


def test_projection_fastapi_endpoint() -> None:
    row = load_sample_row()
    client = TestClient(create_app())

    response = client.post(
        "/projections/calculate",
        json={
            "run_date": "2026-01-01",
            "projected_months": 1,
            "core_info": [row],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["output_successful_records"] == 1
    assert len(payload["projections"]) == 2
    assert payload["projection_dates"] == ["2026-01-01", "2026-01-31"]


def test_projection_v1_fastapi_contract() -> None:
    row = load_sample_row()
    client = TestClient(create_app())

    response = client.post(
        "/v1/projections/calculate",
        json={
            "run_date": "2026-01-01",
            "projected_months": 1,
            "core_info": [row],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["projection_engine_version"] == "rwa-projection-alpha-0.1.0"
    assert payload["summary"]["output_successful_projection_records"] == 2
