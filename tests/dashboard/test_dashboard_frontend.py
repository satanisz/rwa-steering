from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_dashboard_does_not_render_runoff_selector() -> None:
    """The Streamlit dashboard should expose the fixed run-off workflow without a selector."""
    app = AppTest.from_file("src/rwa_dashboard/streamlit_app.py")
    app.run(timeout=60)

    assert len(app.sidebar.segmented_control) == 0
    assert len(app.sidebar.radio) == 0
    assert len(app.exception) == 0
