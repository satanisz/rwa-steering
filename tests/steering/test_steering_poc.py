from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from rwa_calculator.paths import PREPROD_CORE_INFO_PATH
from rwa_steering.engine import RwaSteeringService
from rwa_steering.fastapi_app import create_app
from rwa_steering.schemas import SteeringRequest
from rwa_steering.transformations import migrate_rating


def load_rows(count: int = 10) -> list[dict[str, str]]:
    with PREPROD_CORE_INFO_PATH.open(newline="", encoding="utf-8") as handle:
        return [row for _, row in zip(range(count), csv.DictReader(handle), strict=False)]


def test_rating_migration_moves_down_and_up_on_nccr_scale() -> None:
    assert migrate_rating("3.1", 2) == "3.3"
    assert migrate_rating("3.1", -2) == "2.1"
    assert migrate_rating("0.1", -3) == "0.1"
    assert migrate_rating("8.3", 3) == "8.3"


def test_steering_poc_runs_scenarios_attribution_and_recommendations() -> None:
    rows = load_rows()
    response = RwaSteeringService().run(
        SteeringRequest(
            as_of_date=date(2026, 1, 1),
            projection_dates=[date(2026, 12, 31), date(2027, 12, 31)],
            scenarios=["BASE", "STRESS"],
            core_info=rows,
            top_n_recommendations=5,
        )
    )

    assert response.methodology.startswith("Regime-aware RWA steering")
    assert len(response.summaries) == 4
    assert len(response.attributions) == 4
    assert len(response.projections) == 40
    assert response.recommendations
    assert all(
        projection.sector == rows_by_id(rows)[projection.id]["sector"]
        for projection in response.projections
    )
    assert all(recommendation.sector for recommendation in response.recommendations)
    assert response.recommendations == sorted(
        response.recommendations,
        key=lambda item: item.recommendation_score,
        reverse=True,
    )
    assert {summary.scenario_id for summary in response.summaries} == {"BASE", "STRESS"}
    assert any(
        attribution.interaction_or_residual_delta is not None
        for attribution in response.attributions
    )
    assert all(
        recommendation.estimated_rwa_saving >= Decimal("0")
        for recommendation in response.recommendations
    )


def test_steering_stress_projection_contains_rating_deterioration() -> None:
    row = load_rows(1)[0]
    response = RwaSteeringService().run(
        SteeringRequest(
            as_of_date=date(2026, 1, 1),
            projection_dates=[date(2026, 12, 31)],
            scenarios=["STRESS"],
            core_info=[row],
        )
    )

    projection = response.projections[0]

    assert projection.scenario_id == "STRESS"
    assert projection.sector == row["sector"]
    assert projection.current_rating == row["counterparty_fcy_internal_rating"]
    assert projection.projected_rating != projection.current_rating
    assert projection.projected_dlgd >= projection.current_dlgd


def rows_by_id(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["id"]: row for row in rows}


def test_steering_fastapi_endpoint() -> None:
    rows = load_rows(2)
    client = TestClient(create_app())

    response = client.post(
        "/steering/run",
        json={
            "as_of_date": "2026-01-01",
            "projection_dates": ["2026-12-31"],
            "scenarios": ["BASE"],
            "core_info": rows,
            "top_n_recommendations": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["jurisdiction"] == "EU_CRR3_EBA"
    assert len(payload["summaries"]) == 1
    assert len(payload["projections"]) == 2


def test_steering_v1_contract_and_structured_error() -> None:
    rows = load_rows(2)
    client = TestClient(create_app())

    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["input_package_validation_status"] == "PASSED"

    response = client.post(
        "/v1/steering/run",
        json={
            "as_of_date": "2026-01-01",
            "projection_dates": ["2026-12-31"],
            "scenarios": ["BASE"],
            "jurisdiction": "NO_SUCH_OVERLAY",
            "core_info": rows,
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["api_version"] == "v1"
    assert payload["error"]["code"] == "UNKNOWN_JURISDICTION_OVERLAY"
    assert payload["error"]["field_path"] == "jurisdiction"


def test_steering_openapi_exposes_versioned_endpoint() -> None:
    client = TestClient(create_app())

    openapi = client.get("/openapi.json").json()

    assert "/v1/steering/run" in openapi["paths"]
    assert "/steering/run" in openapi["paths"]
