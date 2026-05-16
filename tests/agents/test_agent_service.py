from __future__ import annotations

from datetime import date

from rwa_agent_service import BriefingRequest, RwaAgentService
from rwa_agent_service.config import AgentServiceSettings
from rwa_agent_service.graph import RwaAgentGraph
from rwa_agent_service.rag import InMemoryEvidenceRetriever
from rwa_agent_service.schemas import AgentFinding, AgentResult, CommentaryRequest, MetricFact
from rwa_agent_service.tools import AgentRuntimeContext
from rwa_dashboard.data import (
    current_rwa_snapshot,
    input_package_overview,
    model_run_set,
    regulatory_capital_snapshot,
)


def test_agent_graph_uses_langgraph_backend() -> None:
    graph = RwaAgentGraph()

    assert graph.backend_name == "langgraph"


def test_agent_service_runs_from_calculated_dashboard_context() -> None:
    as_of_date = date(2026, 5, 15)
    context = AgentRuntimeContext(
        as_of_date=as_of_date,
        scenario_id="BASE",
        snapshot=current_rwa_snapshot(as_of_date, row_limit=10),
        capital=regulatory_capital_snapshot(as_of_date),
        overview=input_package_overview(),
        runs=model_run_set(
            as_of_date=as_of_date,
            scenario_id="BASE",
            runoff_months=2,
            runoff_assets=3,
            forecast_assets=3,
            monte_carlo_horizon_months=2,
            monte_carlo_paths=2,
            monte_carlo_assets=3,
            steering_assets=3,
            steering_recommendations=2,
            rats_assets=4,
            rats_candidates=6,
            rats_legs=2,
            rats_particles=4,
            rats_iterations=3,
        ),
    )
    service = RwaAgentService(settings=AgentServiceSettings(llm_provider="deterministic"))

    response = service.run_from_context(
        BriefingRequest(as_of_date=as_of_date, scenario_id="BASE", request_id="agent-test"),
        context,
    )

    assert response.request_id == "agent-test"
    assert response.status == "COMPLETED"
    assert response.observability.graph_backend == "langgraph"
    assert response.observability.llm_provider == "deterministic"
    assert {result.agent_name for result in response.agent_results} == {
        "RWA Movement Agent",
        "Capital Stack Agent",
        "Data Quality Agent",
        "Evidence Pack Agent",
        "Board Commentary Agent",
    }
    assert response.board_commentary.key_messages
    assert any(item.artifact_type == "prepared_input_file" for item in response.evidence_inventory)
    assert all(result.evidence for result in response.agent_results)


def test_agent_commentary_uses_provided_agent_results_only() -> None:
    service = RwaAgentService(settings=AgentServiceSettings(llm_provider="deterministic"))
    commentary = service.generate_commentary(
        CommentaryRequest(
            as_of_date=date(2026, 5, 15),
            scenario_id="BASE",
            agent_results=[
                AgentResult(
                    agent_name="RWA Movement Agent",
                    status="COMPLETED",
                    summary="Two calculated model outputs are present.",
                    findings=[
                        AgentFinding(
                            title="Movement",
                            severity="WATCH",
                            summary="Forecast scenarios move RWA by PLN 10.0m.",
                        )
                    ],
                ),
                AgentResult(
                    agent_name="Capital Stack Agent",
                    status="COMPLETED",
                    summary="CET1 ratio is 14.0%.",
                ),
                AgentResult(
                    agent_name="Data Quality Agent",
                    status="COMPLETED",
                    summary="Input package is PASSED.",
                ),
                AgentResult(
                    agent_name="Evidence Pack Agent",
                    status="COMPLETED",
                    summary="Evidence pack contains hashed files.",
                ),
            ],
            metric_facts=[
                MetricFact(
                    name="applicable_total_rwa",
                    value="100000000",
                    unit="PLN",
                    source="test",
                ),
                MetricFact(name="cet1_ratio", value="0.14", unit="ratio", source="test"),
                MetricFact(name="leverage_ratio", value="0.05", unit="ratio", source="test"),
                MetricFact(name="data_quality_findings", value=2, unit="count", source="test"),
            ],
        )
    )

    assert "PLN 100.0m" in commentary.executive_summary
    assert commentary.risk_watchlist == ["Forecast scenarios move RWA by PLN 10.0m."]


def test_in_memory_retriever_returns_relevant_evidence() -> None:
    as_of_date = date(2026, 5, 15)
    context = AgentRuntimeContext(
        as_of_date=as_of_date,
        scenario_id="BASE",
        snapshot=current_rwa_snapshot(as_of_date, row_limit=3),
        capital=regulatory_capital_snapshot(as_of_date),
        overview=input_package_overview(),
        runs=model_run_set(
            as_of_date=as_of_date,
            scenario_id="BASE",
            runoff_months=1,
            runoff_assets=3,
            forecast_assets=3,
            monte_carlo_horizon_months=1,
            monte_carlo_paths=2,
            monte_carlo_assets=3,
            steering_assets=3,
            steering_recommendations=1,
            rats_assets=4,
            rats_candidates=4,
            rats_legs=2,
            rats_particles=4,
            rats_iterations=1,
        ),
    )
    service = RwaAgentService(settings=AgentServiceSettings(llm_provider="deterministic"))
    evidence = service.evidence_from_context(
        BriefingRequest(as_of_date=as_of_date, scenario_id="BASE"),
        context,
    )
    retriever = InMemoryEvidenceRetriever()
    retriever.index(evidence.evidence_inventory)

    results = retriever.retrieve("capital stack calculated output floor", limit=3)

    assert results
    assert any("capital" in item.title.lower() for item in results)
