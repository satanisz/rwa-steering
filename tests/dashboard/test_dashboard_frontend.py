from __future__ import annotations

from streamlit.testing.v1 import AppTest

from rwa_dashboard.streamlit_app import APP_PAGES


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
