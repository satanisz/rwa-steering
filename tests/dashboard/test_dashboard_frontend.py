from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_dashboard_exposes_only_runoff_methodology() -> None:
    """Exercise the Streamlit model switch exactly as the dashboard runtime sees it."""
    app = AppTest.from_file("src/rwa_dashboard/streamlit_app.py")
    app.run(timeout=60)

    selector = app.sidebar.segmented_control[0]
    assert selector.options == ["Run-off f(x,t)"]
    assert selector.value == "Run-off f(x,t)"
    assert len(app.exception) == 0
