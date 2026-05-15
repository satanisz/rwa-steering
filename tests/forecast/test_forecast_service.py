from __future__ import annotations

import csv
from datetime import date

from fastapi.testclient import TestClient

from rwa_calculator.paths import PREPROD_CORE_INFO_PATH
from rwa_forecast_service.engine import FORECAST_ENGINE_VERSION, RwaForecastService
from rwa_forecast_service.fastapi_app import create_app
from rwa_forecast_service.schemas import ForecastRequest


def load_rows(count: int = 5) -> list[dict[str, str]]:
    """Load a deterministic portfolio slice for forecast tests."""
    with PREPROD_CORE_INFO_PATH.open(newline="", encoding="utf-8") as handle:
        return [row for _, row in zip(range(count), csv.DictReader(handle), strict=False)]


def test_var_forecast_generates_monte_carlo_paths_and_scores() -> None:
    request = ForecastRequest(
        as_of_date=date(2026, 5, 15),
        horizon_months=6,
        path_count=4,
        model_type="VAR",
        scenario_id="BASE",
        core_info=load_rows(),
        random_seed=42,
        return_top_paths=3,
    )

    response = RwaForecastService().run(request)

    assert response.forecast_engine_version == FORECAST_ENGINE_VERSION
    assert response.summary.path_count == 4
    assert response.summary.horizon_months == 6
    assert response.summary.selected_path_id in {0, 1, 2, 3}
    assert len(response.market_paths) == 4 * 7
    assert len(response.portfolio_paths) == 4 * 7
    assert len(response.path_scores) == 3
    assert response.selected_path
    assert all(score.terminal_rwa >= 0 for score in response.path_scores)


def test_lstm_recurrent_forecast_uses_recurrent_path_generation() -> None:
    request = ForecastRequest(
        as_of_date=date(2026, 5, 15),
        horizon_months=3,
        path_count=3,
        model_type="LSTM_RECURRENT",
        scenario_id="STRESS",
        core_info=load_rows(3),
        random_seed=99,
        return_top_paths=2,
    )

    response = RwaForecastService().run(request)

    assert response.summary.model_type == "LSTM_RECURRENT"
    assert response.summary.breach_probability >= 0
    assert {step.model_type for step in response.market_paths} == {"LSTM_RECURRENT"}


def test_forecast_fastapi_endpoint() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v1/forecasts/run",
        json={
            "as_of_date": "2026-05-15",
            "horizon_months": 2,
            "path_count": 2,
            "model_type": "VAR",
            "scenario_id": "BASE",
            "core_info": load_rows(3),
            "random_seed": 123,
            "return_top_paths": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["forecast_engine_version"] == FORECAST_ENGINE_VERSION
    assert payload["summary"]["path_count"] == 2
    assert len(payload["selected_path"]) == 3
