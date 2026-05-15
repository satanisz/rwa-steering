from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_steering_dashboard_switches_between_three_models() -> None:
    """Exercise the Streamlit model switch exactly as the dashboard runtime sees it."""
    app = AppTest.from_file("src/rwa_dashboard/streamlit_app.py")
    app.run(timeout=60)

    selector = app.sidebar.segmented_control[0]
    assert selector.options == ["Run-off f(x,t)", "Forecast Monte Carlo", "RATS optimizer"]
    assert selector.value == "Forecast Monte Carlo"
    assert len(app.exception) == 0

    for model_name in ["Run-off f(x,t)", "RATS optimizer", "Forecast Monte Carlo"]:
        selector.set_value(model_name)
        app.run(timeout=90)

        selector = app.sidebar.segmented_control[0]
        assert selector.value == model_name
        assert len(app.exception) == 0
