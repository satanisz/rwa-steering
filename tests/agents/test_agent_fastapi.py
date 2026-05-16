from __future__ import annotations

from fastapi.testclient import TestClient

from rwa_agent_service.fastapi_app import create_app


def test_agent_health_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("RWA_AGENT_LLM_PROVIDER", "deterministic")
    client = TestClient(create_app())

    response = client.get("/v1/agents/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "rwa-agent-service"
    assert payload["status"] == "ok"
    assert payload["llm_provider"] in {"deterministic", "ollama"}


def test_agent_commentary_endpoint_returns_structured_json(monkeypatch) -> None:
    monkeypatch.setenv("RWA_AGENT_LLM_PROVIDER", "deterministic")
    client = TestClient(create_app())

    response = client.post(
        "/v1/agents/commentary/run",
        json={
            "as_of_date": "2026-05-15",
            "scenario_id": "BASE",
            "agent_results": [
                {
                    "agent_name": "RWA Movement Agent",
                    "status": "COMPLETED",
                    "summary": "Calculated movement is available.",
                    "findings": [],
                    "evidence": [],
                    "limitations": [],
                    "confidence": "1.0",
                },
                {
                    "agent_name": "Capital Stack Agent",
                    "status": "COMPLETED",
                    "summary": "Capital stack is available.",
                    "findings": [],
                    "evidence": [],
                    "limitations": [],
                    "confidence": "1.0",
                },
                {
                    "agent_name": "Data Quality Agent",
                    "status": "COMPLETED",
                    "summary": "Input validation passed.",
                    "findings": [],
                    "evidence": [],
                    "limitations": [],
                    "confidence": "1.0",
                },
                {
                    "agent_name": "Evidence Pack Agent",
                    "status": "COMPLETED",
                    "summary": "Evidence inventory is available.",
                    "findings": [],
                    "evidence": [],
                    "limitations": [],
                    "confidence": "1.0",
                },
            ],
            "metric_facts": [
                {
                    "name": "applicable_total_rwa",
                    "value": "100000000",
                    "unit": "PLN",
                    "source": "test",
                },
                {
                    "name": "cet1_ratio",
                    "value": "0.14",
                    "unit": "ratio",
                    "source": "test",
                },
                {
                    "name": "leverage_ratio",
                    "value": "0.05",
                    "unit": "ratio",
                    "source": "test",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["executive_summary"]
    assert payload["source_agent_names"] == [
        "RWA Movement Agent",
        "Capital Stack Agent",
        "Data Quality Agent",
        "Evidence Pack Agent",
    ]
