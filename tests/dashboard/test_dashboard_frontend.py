from __future__ import annotations

from datetime import date

from streamlit.testing.v1 import AppTest

from rwa_dashboard.data import current_rwa_snapshot
from rwa_dashboard.streamlit_app import APP_PAGES, build_rwa_commentary_request


def test_dashboard_sidebar_routes_to_concept_pages(monkeypatch) -> None:
    """Exercise real page routing for the concept sidebar pages."""
    monkeypatch.setenv("RWA_AGENT_LLM_PROVIDER", "deterministic")
    app = AppTest.from_file("src/rwa_dashboard/streamlit_app.py")
    app.run(timeout=120)

    navigation = app.sidebar.radio[0]
    assert navigation.options == list(APP_PAGES)
    assert navigation.value == "RWA Dashboard"
    selector = app.sidebar.segmented_control[0]
    assert selector.options == [
        "Run-off f(x,t)",
        "Forecast scenarios",
        "Forecast Monte Carlo",
        "Scenario steering",
        "RATS optimizer",
    ]
    assert selector.value == "Forecast Monte Carlo"
    assert len(app.exception) == 0

    for page_name in [
        "Scenario Analysis",
        "Data Lineage",
        "Reports & Evidence",
        "RWA Intelligence Briefing",
    ]:
        navigation = app.sidebar.radio[0]
        navigation.set_value(page_name)
        app.run(timeout=120)

        assert app.sidebar.radio[0].value == page_name
        assert len(app.exception) == 0

    assert [tab.label for tab in app.tabs] == ["Executive Summary", "CRO View", "CFO View"]
    assert any("AI Executive Commentary" in item.value for item in app.markdown)
    assert any("Generated " in item.value for item in app.markdown)
    assert any(button.label == "Regenerate" for button in app.button)


def test_ai_commentary_request_uses_structured_anonymized_calculated_rows() -> None:
    snapshot = current_rwa_snapshot(date(2026, 5, 15), row_limit=3)

    request = build_rwa_commentary_request(
        snapshot,
        request_id="frontend-contract",
        scenario_id="BASE",
    )

    assert len(request.rwa_input_data) == 3
    assert len(request.rwa_output_results) == 3
    assert request.rwa_input_data[0].asset_id.startswith("EXP")
    assert request.rwa_output_results[0].rwa_amount >= 0
    assert all(record.sector for record in request.rwa_input_data)
    assert all(output.approach == "Basel 3.1 final" for output in request.rwa_output_results)
    assert all(not record.parameters for record in request.rwa_input_data)
