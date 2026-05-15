from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from rwa_calculator.paths import PREPROD_CORE_INFO_PATH
from rwa_rats_service.engine import RATS_ENGINE_VERSION, RwaRATSService
from rwa_rats_service.fastapi_app import create_app
from rwa_rats_service.schemas import RATSConstraints, RATSRequest, SwarmSettings


def load_rows(count: int = 8) -> list[dict[str, str]]:
    """Load a small deterministic portfolio slice for fast RATS tests."""
    with PREPROD_CORE_INFO_PATH.open(newline="", encoding="utf-8") as handle:
        return [row for _, row in zip(range(count), csv.DictReader(handle), strict=False)]


def test_rats_service_optimizes_forecasted_rwa_with_swarm() -> None:
    request = RATSRequest(
        as_of_date=date(2026, 5, 15),
        projection_date=date(2026, 12, 31),
        scenario_id="STRESS",
        core_info=load_rows(),
        top_n_candidates=10,
        constraints=RATSConstraints(max_strategy_legs=3, max_total_reduction_pct=Decimal("0.30")),
        swarm=SwarmSettings(particles=8, iterations=6, max_stall_iterations=3, random_seed=7),
    )

    response = RwaRATSService().optimize(request)

    assert response.rats_engine_version == RATS_ENGINE_VERSION
    assert response.summary.projected_rwa_before_strategy > Decimal("0")
    assert (
        response.summary.optimized_projected_rwa <= response.summary.projected_rwa_before_strategy
    )
    assert response.summary.rwa_saving >= Decimal("0")
    assert response.summary.selected_legs <= request.constraints.max_strategy_legs
    assert len(response.candidates) <= request.top_n_candidates
    assert all(candidate.sector for candidate in response.candidates)
    assert all(leg.sector for leg in response.best_strategy)
    assert response.convergence
    assert all(leg.reduction_pct > Decimal("0") for leg in response.best_strategy)


def test_rats_fastapi_endpoint() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/rats/optimize",
        json={
            "as_of_date": "2026-05-15",
            "projection_date": "2026-12-31",
            "scenario_id": "BASE",
            "core_info": load_rows(4),
            "top_n_candidates": 6,
            "constraints": {
                "max_strategy_legs": 2,
                "max_total_reduction_pct": "0.25",
            },
            "swarm": {
                "particles": 4,
                "iterations": 3,
                "max_stall_iterations": 2,
                "random_seed": 11,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rats_engine_version"] == RATS_ENGINE_VERSION
    assert (
        payload["summary"]["projected_rwa_before_strategy"]
        >= payload["summary"]["optimized_projected_rwa"]
    )
    assert all(candidate["sector"] for candidate in payload["candidates"])
    assert len(payload["best_strategy"]) <= 2
