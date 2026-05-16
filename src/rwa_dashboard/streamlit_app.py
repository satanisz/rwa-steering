from __future__ import annotations

import asyncio
import html
from datetime import date
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from rwa_agent_service import BriefingRequest, MultiAgentRwaAnalysisRequest, RwaAgentService
from rwa_agent_service.tools import AgentRuntimeContext
from rwa_dashboard.data import (
    RWA_FINAL_FIELD,
    RWA_FOUNDATION_FIELD,
    RWA_STANDARDISED_FIELD,
    available_projection_dates,
    current_rwa_snapshot,
    default_as_of_date,
    forecast_projection,
    input_package_overview,
    model_run_set,
    monte_carlo_forecast,
    rats_optimization,
    regulatory_capital_snapshot,
    runoff_projection,
    steering_simulation,
)

RWA_LABELS = {
    "basel_3_0_rwa": "Basel 3.0",
    RWA_FOUNDATION_FIELD: "Basel 3.1 foundation",
    RWA_STANDARDISED_FIELD: "Basel 3.1 standardised",
    RWA_FINAL_FIELD: "Basel 3.1 final",
}
RWA_FINAL_RISK_WEIGHT_FIELD = "basel_3_1_rw_final"
MODEL_RUNOFF = "Run-off f(x,t)"
MODEL_SCENARIO_FORECAST = "Forecast scenarios"
MODEL_FORECAST = "Forecast Monte Carlo"
MODEL_STEERING = "Scenario steering"
MODEL_RATS = "RATS optimizer"
STEERING_MODEL_OPTIONS = (
    MODEL_RUNOFF,
    MODEL_SCENARIO_FORECAST,
    MODEL_FORECAST,
    MODEL_STEERING,
    MODEL_RATS,
)
SCENARIO_OPTIONS = ("BASE", "DOWNSIDE", "STRESS", "RECOVERY")
FORECAST_ENGINE_OPTIONS = ("VAR", "LSTM_PROXY")
AGENT_SLOT_NAMES = (
    "RWA Movement Agent",
    "Capital Stack Agent",
    "Data Quality Agent",
    "Evidence Pack Agent",
    "Board Commentary Agent",
)
APP_PAGES = (
    "Exposure Upload",
    "RWA Dashboard",
    "Portfolio Analytics",
    "Scenario Analysis",
    "Data Lineage",
    "Reports & Evidence",
    "RWA Intelligence Briefing",
)

CONTROL_TOWER_CSS = """
<style>
:root {
    --tower-navy: #06142d;
    --tower-blue: #0b5cff;
    --tower-border: #dce5f2;
    --tower-muted: #5f6f89;
    --tower-text: #07142f;
    --tower-panel: #ffffff;
    --tower-bg: #f6f8fc;
    --tower-success: #16a34a;
    --tower-warn: #d97706;
}

.stApp {
    background: var(--tower-bg);
    color: var(--tower-text);
}

[data-testid="stHeader"] {
    background: rgba(255, 255, 255, 0.94);
    border-bottom: 1px solid var(--tower-border);
}

[data-testid="stAppViewContainer"] > .main .block-container {
    max-width: 100%;
    padding: 1.1rem 1.6rem 2rem;
}

section[data-testid="stSidebar"] > div:first-child {
    background: linear-gradient(180deg, #071a38 0%, #031024 100%);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span {
    color: #edf4ff;
}

section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
    color: #edf4ff;
}

section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] [data-baseweb="select"] span,
section[data-testid="stSidebar"] [data-baseweb="input"] span {
    color: var(--tower-text);
}

.tower-brand {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin: 0.25rem 0 1.35rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}

.tower-logo {
    width: 2.35rem;
    height: 2.35rem;
    border: 1px solid rgba(255, 255, 255, 0.42);
    border-radius: 8px;
    display: grid;
    place-items: center;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0;
}

.tower-brand-title {
    font-weight: 800;
    font-size: 1rem;
    line-height: 1.15;
}

.tower-brand-subtitle,
.sidebar-section-label {
    color: #aab8cf;
    font-size: 0.78rem;
}

.sidebar-section-label {
    margin: 1rem 0 0.4rem;
    font-weight: 700;
    text-transform: uppercase;
}

.tower-nav-item {
    padding: 0.58rem 0.7rem;
    margin: 0.12rem 0;
    border-radius: 8px;
    color: #dce8ff;
    font-size: 0.88rem;
}

.tower-nav-item.active {
    background: linear-gradient(90deg, rgba(11, 92, 255, 0.95), rgba(98, 65, 220, 0.82));
    color: #ffffff;
    font-weight: 750;
}

.tower-sidebar-status {
    margin-top: 1rem;
    padding: 0.85rem;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.05);
}

.status-row {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    margin-top: 0.48rem;
    font-size: 0.8rem;
}

.status-ok {
    color: #22c55e;
    font-weight: 700;
}

.tower-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.15rem 0 0.85rem;
    border-bottom: 1px solid var(--tower-border);
}

.tower-breadcrumb {
    color: #354461;
    font-size: 0.86rem;
}

.tower-actions {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    flex-wrap: wrap;
    justify-content: flex-end;
}

.tower-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.32rem 0.58rem;
    border: 1px solid var(--tower-border);
    border-radius: 8px;
    background: #ffffff;
    color: #243452;
    font-size: 0.78rem;
    font-weight: 700;
}

.tower-pill.success {
    background: #eaf8ef;
    color: #087433;
    border-color: #c8efd4;
}

.tower-title-row {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 1rem;
    padding: 1.2rem 0 0.8rem;
}

.tower-title {
    font-size: 2rem;
    line-height: 1.1;
    font-weight: 820;
    color: var(--tower-text);
}

.tower-subtitle {
    margin-top: 0.35rem;
    color: var(--tower-muted);
    font-size: 0.96rem;
}

[data-testid="stMetric"] {
    min-height: 112px;
    padding: 1rem 1.08rem;
    background: var(--tower-panel);
    border: 1px solid var(--tower-border);
    border-radius: 8px;
    box-shadow: 0 10px 24px rgba(8, 25, 56, 0.04);
}

[data-testid="stMetricLabel"] {
    color: #52637d;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0;
}

[data-testid="stMetricValue"] {
    color: var(--tower-text);
    font-weight: 820;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: var(--tower-border);
    border-radius: 8px;
    background: var(--tower-panel);
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.65rem;
    border-bottom: 1px solid var(--tower-border);
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 0.65rem 0.9rem;
}

.stTabs [aria-selected="true"] {
    color: var(--tower-blue);
    background: #eef4ff;
}

.stButton > button,
.stDownloadButton > button {
    border-radius: 8px;
    border: 1px solid var(--tower-border);
    font-weight: 750;
}

.agent-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.75rem;
}

.agent-card,
.briefing-card,
.trace-card {
    border: 1px solid var(--tower-border);
    border-radius: 8px;
    background: #ffffff;
    padding: 0.9rem;
    box-shadow: 0 10px 24px rgba(8, 25, 56, 0.04);
}

.agent-card h4,
.briefing-card h4,
.trace-card h4 {
    margin: 0 0 0.35rem;
    color: var(--tower-text);
    font-size: 0.95rem;
}

.agent-card p,
.briefing-card p,
.trace-card p {
    margin: 0.25rem 0 0;
    color: var(--tower-muted);
    font-size: 0.82rem;
}

.agent-status {
    display: inline-flex;
    margin-top: 0.7rem;
    padding: 0.22rem 0.5rem;
    border-radius: 8px;
    background: #eaf8ef;
    color: #087433;
    font-size: 0.75rem;
    font-weight: 780;
}

.agent-status.reserved {
    background: #eef4ff;
    color: #0b5cff;
}

.ai-commentary-shell {
    border: 1px solid var(--tower-border);
    border-radius: 8px;
    background: #ffffff;
    padding: 0.95rem;
    box-shadow: 0 10px 24px rgba(8, 25, 56, 0.04);
}

.ai-commentary-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin-bottom: 0.55rem;
}

.ai-commentary-title h4 {
    margin: 0;
    color: var(--tower-text);
    font-size: 1rem;
}

.ai-commentary-copy {
    color: #192943;
    font-size: 0.9rem;
    line-height: 1.55;
    margin: 0.2rem 0 0.75rem;
}

.ai-commentary-meta {
    color: var(--tower-muted);
    font-size: 0.78rem;
    margin-top: 0.7rem;
}

.commentary-checklist {
    display: grid;
    gap: 0.42rem;
    margin-top: 0.45rem;
}

.commentary-check {
    display: flex;
    align-items: flex-start;
    gap: 0.48rem;
    color: #1c2d48;
    font-size: 0.84rem;
}

.commentary-checkmark {
    width: 1rem;
    height: 1rem;
    min-width: 1rem;
    border-radius: 999px;
    background: #eaf8ef;
    color: #087433;
    display: inline-grid;
    place-items: center;
    font-size: 0.68rem;
    font-weight: 800;
    margin-top: 0.12rem;
}

.evidence-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    gap: 0.85rem;
}

@media (max-width: 1100px) {
    .tower-topbar,
    .tower-title-row {
        align-items: flex-start;
        flex-direction: column;
    }

    .agent-grid,
    .evidence-strip {
        grid-template-columns: 1fr;
    }
}
</style>
"""


@st.cache_data(ttl=600, show_spinner=False)
def cached_current(as_of_date: date):
    """Cache current RWA calculation across Streamlit reruns."""
    return current_rwa_snapshot(as_of_date)


@st.cache_data(ttl=600, show_spinner=False)
def cached_runoff_projection(as_of_date: date, months: int, assets: int):
    """Cache closed-book run-off projection output across Streamlit reruns."""
    return runoff_projection(as_of_date, projected_months=months, top_n_assets=assets)


@st.cache_data(ttl=600, show_spinner=False)
def cached_forecast_projection(as_of_date: date, assets: int):
    """Cache deterministic multi-scenario forecast output across Streamlit reruns."""
    return forecast_projection(as_of_date, scenarios=list(SCENARIO_OPTIONS), top_n_assets=assets)


@st.cache_data(ttl=600, show_spinner=False)
def cached_monte_carlo_forecast(
    as_of_date: date,
    scenario_id: str,
    model_type: str,
    horizon_months: int,
    path_count: int,
    assets: int,
):
    """Cache VAR/LSTM Monte Carlo forecast output across Streamlit reruns."""
    return monte_carlo_forecast(
        as_of_date=as_of_date,
        scenario_id=scenario_id,
        model_type=model_type,
        horizon_months=horizon_months,
        path_count=path_count,
        top_n_assets=assets,
    )


@st.cache_data(ttl=600, show_spinner=False)
def cached_rats_optimization(
    as_of_date: date,
    projection_date: date,
    scenario_id: str,
    assets: int,
    candidates: int,
    legs: int,
    particles: int,
    iterations: int,
):
    """Cache RATS optimizer output across Streamlit reruns."""
    return rats_optimization(
        as_of_date=as_of_date,
        projection_date=projection_date,
        scenario_id=scenario_id,
        top_n_assets=assets,
        top_n_candidates=candidates,
        max_strategy_legs=legs,
        particles=particles,
        iterations=iterations,
    )


@st.cache_data(ttl=600, show_spinner=False)
def cached_steering_simulation(
    as_of_date: date,
    scenario_id: str,
    assets: int,
    recommendations: int,
):
    """Cache deterministic steering scenario output across Streamlit reruns."""
    return steering_simulation(
        as_of_date=as_of_date,
        scenarios=[scenario_id],
        top_n_assets=assets,
        top_n_recommendations=recommendations,
    )


@st.cache_data(ttl=600, show_spinner=False)
def cached_regulatory_capital(as_of_date: date):
    """Cache portfolio-level Basel capital module output across Streamlit reruns."""
    return regulatory_capital_snapshot(as_of_date)


@st.cache_data(ttl=600, show_spinner=False)
def cached_input_package():
    """Cache generated-input metadata across Streamlit reruns."""
    return input_package_overview()


@st.cache_data(ttl=600, show_spinner=False)
def cached_model_run_set(as_of_date: date, scenario_id: str):
    """Cache calculated outputs for all dashboard model surfaces."""
    return model_run_set(
        as_of_date=as_of_date,
        scenario_id=scenario_id,
        runoff_assets=50,
        forecast_assets=25,
        monte_carlo_assets=15,
        steering_assets=25,
        rats_assets=15,
        rats_candidates=12,
        rats_particles=6,
        rats_iterations=5,
    )


def apply_control_tower_theme() -> None:
    """Apply the Control Tower visual layer used by the dashboard shell."""
    st.markdown(CONTROL_TOWER_CSS, unsafe_allow_html=True)


def render_control_tower_sidebar(overview) -> str:
    """Render real page navigation and package health in the Streamlit sidebar."""
    generated_files = len(overview.manifest["generated_files"])
    quality_gates = len(overview.validation_report["quality_gates"])
    validation_status = overview.manifest["validation_status"]
    st.sidebar.markdown(
        """
        <div class="tower-brand">
            <div class="tower-logo">RWA</div>
            <div>
                <div class="tower-brand-title">RWA Control Tower</div>
                <div class="tower-brand-subtitle">RWA Capital Engine</div>
            </div>
        </div>
        <div class="sidebar-section-label">Navigation</div>
        """,
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio(
        "Navigation",
        APP_PAGES,
        index=APP_PAGES.index("RWA Dashboard"),
        label_visibility="collapsed",
        key="app_page",
    )
    st.sidebar.markdown(
        f"""
        <div class="sidebar-section-label">Controls</div>
        <div class="tower-sidebar-status">
            <strong>System status</strong>
            <div class="status-row">
                <span>Input package</span>
                <span class="status-ok">{validation_status}</span>
            </div>
            <div class="status-row">
                <span>Prepared files</span><span>{generated_files}</span>
            </div>
            <div class="status-row">
                <span>Quality gates</span><span>{quality_gates}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return str(page)


def render_page_header(
    page: str,
    as_of_date: date,
    selected_model: str,
    scenario_id: str,
    overview,
) -> None:
    """Render the dashboard topbar and page title in the concept style."""
    package_version = display_version(overview.manifest["version_id"])
    validation_status = overview.manifest["validation_status"]
    st.markdown(
        f"""
        <div class="tower-topbar">
            <div class="tower-breadcrumb">
                Home &gt; {page} &gt; {selected_model}
            </div>
            <div class="tower-actions">
                <span class="tower-pill success">PREPROD</span>
                <span class="tower-pill">Reporting date {as_of_date.isoformat()}</span>
                <span class="tower-pill">Scenario {scenario_id}</span>
                <span class="tower-pill">Inputs {validation_status}</span>
            </div>
        </div>
        <div class="tower-title-row">
            <div>
                <div class="tower-title">{page}</div>
                <div class="tower-subtitle">
                    Prepared input package {package_version}; calculations use generated CSV data
                    and calculator outputs, not inline fallback values.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    """Render the RWA steering simulation dashboard."""
    st.set_page_config(page_title="RWA Control Tower", layout="wide")
    apply_control_tower_theme()

    default_date = default_as_of_date()
    overview = cached_input_package()
    page = render_control_tower_sidebar(overview)
    as_of_date = st.sidebar.date_input("Reporting date", value=default_date)
    selected_model = model_selector()
    scenario_id = st.sidebar.selectbox(
        "Scenario",
        SCENARIO_OPTIONS,
        index=SCENARIO_OPTIONS.index("STRESS") if selected_model == MODEL_RATS else 0,
    )

    snapshot = cached_current(as_of_date)
    capital = cached_regulatory_capital(as_of_date)
    with st.spinner("Calculating model run set from prepared inputs..."):
        runs = cached_model_run_set(as_of_date, str(scenario_id))

    render_page_header(page, as_of_date, selected_model, str(scenario_id), overview)
    render_page(
        page=page,
        snapshot=snapshot,
        capital=capital,
        overview=overview,
        runs=runs,
        selected_model=selected_model,
        as_of_date=as_of_date,
        scenario_id=str(scenario_id),
    )


def model_selector() -> str:
    """Render the steering model switch with a Streamlit-version-safe fallback."""
    control = getattr(st.sidebar, "segmented_control", None)
    if callable(control):
        return str(
            control(
                "Model drill-down",
                options=STEERING_MODEL_OPTIONS,
                default=MODEL_FORECAST,
            )
            or MODEL_FORECAST
        )
    return str(
        st.sidebar.radio(
            "Model drill-down",
            STEERING_MODEL_OPTIONS,
            index=STEERING_MODEL_OPTIONS.index(MODEL_FORECAST),
        )
    )


def render_page(
    *,
    page: str,
    snapshot,
    capital,
    overview,
    runs,
    selected_model: str,
    as_of_date: date,
    scenario_id: str,
) -> None:
    """Dispatch the selected app page."""
    if page == "Exposure Upload":
        render_exposure_upload(snapshot, overview)
        return
    if page == "RWA Dashboard":
        render_rwa_dashboard(snapshot, capital, runs)
        return
    if page == "Portfolio Analytics":
        render_portfolio_analytics(snapshot, runs)
        return
    if page == "Scenario Analysis":
        render_scenario_analysis(runs, selected_model)
        return
    if page == "Data Lineage":
        render_data_lineage(snapshot, capital, overview, runs)
        return
    if page == "Reports & Evidence":
        render_reports_evidence(snapshot, capital, overview, runs, as_of_date, scenario_id)
        return
    render_agent_briefing(snapshot, capital, overview, as_of_date, runs)


def render_rwa_dashboard(snapshot, capital, runs) -> None:
    """Render the management dashboard with every model output represented."""
    render_current(snapshot)

    st.subheader("Model projection coverage")
    st.dataframe(format_table(runs.model_summary), width="stretch", hide_index=True)

    if not runs.projection_comparison.empty:
        comparison_chart = (
            alt.Chart(runs.projection_comparison)
            .mark_line(point=True)
            .encode(
                x=alt.X("projection_date:T", title="Projection date"),
                y=alt.Y("projected_rwa:Q", title="Projected RWA"),
                color=alt.Color("model:N", title="Model"),
                strokeDash=alt.StrokeDash("scenario_id:N", title="Scenario"),
                tooltip=[
                    "model",
                    "scenario_id",
                    "stage",
                    alt.Tooltip("projection_date:T", title="Projection date"),
                    alt.Tooltip("projected_rwa:Q", format=",.0f"),
                ],
            )
        )
        st.altair_chart(comparison_chart, width="stretch")

    if not runs.sector_projection.empty:
        st.subheader("Projected RWA by sector and model")
        latest_by_model = (
            runs.sector_projection.sort_values("projection_date")
            .groupby(
                ["model", "sector"],
                as_index=False,
                dropna=False,
            )
            .tail(1)
        )
        sector_chart = (
            alt.Chart(latest_by_model)
            .mark_bar()
            .encode(
                x=alt.X("projected_rwa:Q", title="Projected RWA"),
                y=alt.Y("sector:N", title=None, sort="-x"),
                color=alt.Color("model:N", title="Model"),
                tooltip=[
                    "model",
                    "scenario_id",
                    "sector",
                    "stage",
                    alt.Tooltip("projected_rwa:Q", format=",.0f"),
                    "asset_count",
                ],
            )
        )
        st.altair_chart(sector_chart, width="stretch")

    render_regulatory_capital(capital)


def render_exposure_upload(snapshot, overview) -> None:
    """Render prepared exposure input status and portfolio intake diagnostics."""
    col_rows, col_files, col_quality, col_status = st.columns(4)
    col_rows.metric("Exposure rows", snapshot.summary["input_data_records"])
    col_files.metric("Prepared files", len(overview.manifest["generated_files"]))
    col_quality.metric("Quality findings", len(overview.data_quality_flags))
    col_status.metric("Validation status", overview.manifest["validation_status"])

    left, right = st.columns([1.1, 1])
    with left:
        st.subheader("Largest prepared exposures")
        st.dataframe(format_table(snapshot.top_assets), width="stretch", hide_index=True)
    with right:
        render_input_package(overview)


def render_portfolio_analytics(snapshot, runs) -> None:
    """Render current and projected portfolio cuts."""
    entity_sector, projected_sector = st.tabs(["Current portfolio", "Projected sector paths"])
    with entity_sector:
        render_current(snapshot)
    with projected_sector:
        if runs.sector_projection.empty:
            st.info("No sector projection rows were returned for the calculated model set.")
        else:
            st.dataframe(format_table(runs.sector_projection), width="stretch", hide_index=True)


def render_scenario_analysis(runs, selected_model: str) -> None:
    """Render all calculated scenario/model outputs with the selected model first."""
    render_model_run_tabs(runs, selected_model)


def render_model_run_tabs(runs, selected_model: str) -> None:
    """Render model outputs from the shared run set without recalculating services."""
    tab_names = list(STEERING_MODEL_OPTIONS)
    if selected_model in tab_names:
        tab_names = [selected_model, *[name for name in tab_names if name != selected_model]]
    tabs = st.tabs(tab_names)
    for tab, name in zip(tabs, tab_names, strict=True):
        with tab:
            if name == MODEL_RUNOFF:
                render_runoff(runs.runoff)
            elif name == MODEL_SCENARIO_FORECAST:
                render_forecast(runs.forecast)
            elif name == MODEL_FORECAST:
                render_monte_carlo_forecast(runs.monte_carlo)
            elif name == MODEL_STEERING:
                render_steering(runs.steering)
            elif runs.rats is None:
                st.warning("No generated projection date is available for RATS optimization.")
            else:
                render_rats(runs.rats)


def render_data_lineage(snapshot, capital, overview, runs) -> None:
    """Render calculated lineage from source files through models to dashboard pages."""
    lineage = lineage_frame(snapshot, capital, overview, runs)
    st.subheader("Lineage graph")
    st.dataframe(format_table(lineage), width="stretch", hide_index=True)

    edge_chart = (
        alt.Chart(lineage)
        .mark_bar()
        .encode(
            x=alt.X("records:Q", title="Records / artifacts"),
            y=alt.Y("target:N", title=None, sort="-x"),
            color=alt.Color("source:N", title="Source"),
            tooltip=["source", "target", "artifact_type", "status", "records"],
        )
    )
    st.altair_chart(edge_chart, width="stretch")

    st.subheader("Sector propagation")
    sector_coverage = runs.model_summary[["model", "scenario_id", "sector_available", "status"]]
    st.dataframe(format_table(sector_coverage), width="stretch", hide_index=True)


def render_reports_evidence(
    snapshot, capital, overview, runs, as_of_date: date, scenario_id: str
) -> None:
    """Render run evidence, calculated model inventory and prepared input package metadata."""
    col_run, col_models, col_hashes, col_gates = st.columns(4)
    col_run.metric("Run date", as_of_date.isoformat())
    col_models.metric("Calculated models", runs.model_summary["model"].nunique())
    col_hashes.metric("File hashes", len(overview.manifest.get("file_sha256", {})))
    col_gates.metric("Quality gates", len(overview.validation_report["quality_gates"]))

    contents, evidence, controls = st.tabs(["Package contents", "Run evidence", "Control mapping"])
    with contents:
        render_input_package(overview)
    with evidence:
        st.subheader("Model run evidence")
        st.dataframe(format_table(runs.model_summary), width="stretch", hide_index=True)
        st.subheader("Traceability")
        st.markdown(evidence_trace_strip(snapshot, capital, overview, runs), unsafe_allow_html=True)
    with controls:
        control_frame = pd.DataFrame(
            [
                {
                    "control": "Prepared input manifest",
                    "evidence": "Manifest, row counts and SHA-256 hashes",
                    "status": overview.manifest["validation_status"],
                },
                {
                    "control": "Calculator-backed RWA",
                    "evidence": (
                        "Current, run-off, forecast and steering rows revalue through calculator"
                    ),
                    "status": "CALCULATED",
                },
                {
                    "control": "Scenario model propagation",
                    "evidence": (
                        f"Scenario {scenario_id} appears in model summary and projection frames"
                    ),
                    "status": "CALCULATED",
                },
                {
                    "control": "Capital stack",
                    "evidence": ", ".join(capital.capital_stack["component"].tolist()),
                    "status": "CALCULATED",
                },
            ]
        )
        st.dataframe(control_frame, width="stretch", hide_index=True)


def render_selected_model(selected_model: str, as_of_date: date, scenario_id: str) -> None:
    """Run and render exactly one selected steering model."""
    st.subheader(selected_model)
    if selected_model == MODEL_RUNOFF:
        projected_months = st.slider("Run-off horizon in months", 1, 24, 24)
        assets = st.slider("Run-off assets", 10, 300, 100, 10)
        with st.spinner("Calculating current portfolio run-off..."):
            runoff = cached_runoff_projection(as_of_date, projected_months, assets)
        render_runoff(runoff)
        return

    if selected_model == MODEL_SCENARIO_FORECAST:
        assets = st.slider("Scenario forecast assets", 3, 150, 50, 1)
        with st.spinner("Calculating all forecast scenarios..."):
            forecast = cached_forecast_projection(as_of_date, assets)
        render_forecast(forecast)
        return

    if selected_model == MODEL_FORECAST:
        model_type = st.selectbox("Forecast engine", FORECAST_ENGINE_OPTIONS)
        horizon_months = st.slider("Forecast horizon in months", 1, 36, 12)
        path_count = st.slider("Monte Carlo paths", 2, 100, 12, 1)
        assets = st.slider("Forecast assets", 3, 100, 25, 1)
        with st.spinner("Simulating VAR/LSTM and Monte Carlo trajectories..."):
            forecast = cached_monte_carlo_forecast(
                as_of_date,
                scenario_id,
                str(model_type),
                horizon_months,
                path_count,
                assets,
            )
        render_monte_carlo_forecast(forecast)
        return

    if selected_model == MODEL_STEERING:
        assets = st.slider("Steering assets", 3, 150, 50, 1)
        recommendations = st.slider("Recommendations", 1, 25, 10, 1)
        with st.spinner("Calculating scenario steering, attribution and recommendations..."):
            steering = cached_steering_simulation(
                as_of_date,
                scenario_id,
                assets,
                recommendations,
            )
        render_steering(steering)
        return

    projection_dates = available_projection_dates(as_of_date)
    if not projection_dates:
        st.error("No generated projection dates are available for the selected as-of date.")
        return
    projection_date = st.selectbox(
        "Optimization date",
        projection_dates,
        index=len(projection_dates) - 1,
        format_func=lambda value: value.isoformat(),
    )
    assets = st.slider("RATS assets", 4, 80, 25, 1)
    candidates = st.slider("UEI candidates", 4, 50, 20, 1)
    legs = st.slider("Maximum strategy legs", 1, 10, 4, 1)
    particles = st.slider("Particles", 4, 40, 10, 1)
    iterations = st.slider("Iterations", 1, 40, 8, 1)
    with st.spinner("Calculating Risk-Aware Trading Swarm..."):
        rats = cached_rats_optimization(
            as_of_date,
            projection_date,
            scenario_id,
            assets,
            candidates,
            legs,
            particles,
            iterations,
        )
    render_rats(rats)


def render_current(snapshot) -> None:
    """Render point-in-time RWA metrics and portfolio cuts."""
    total_rwa = snapshot.summary[RWA_FINAL_FIELD]
    total_exposure = snapshot.summary["total_exposure_amount"]
    density = snapshot.summary["basel_3_1_rwa_density"]

    col_rwa, col_exposure, col_density, col_failures = st.columns(4)
    col_rwa.metric("Credit RWA final", format_money(total_rwa))
    col_exposure.metric("Exposure amount", format_money(total_exposure))
    col_density.metric("RWA density", format_pct(density))
    col_failures.metric("Validation errors", snapshot.summary["output_failure_records"])

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("RWA by exposure class")
        chart = (
            alt.Chart(snapshot.by_entity)
            .mark_bar()
            .encode(
                x=alt.X("entity_class:N", title="Exposure class"),
                y=alt.Y(f"{RWA_FINAL_FIELD}:Q", title="Basel 3.1 final RWA"),
                color=alt.Color("entity_class:N", legend=None),
                tooltip=[
                    "entity_class",
                    "asset_count",
                    alt.Tooltip("exposure_amount:Q", format=",.0f"),
                    alt.Tooltip(f"{RWA_FINAL_FIELD}:Q", format=",.0f"),
                    alt.Tooltip("rwa_density:Q", format=".2%"),
                ],
            )
        )
        st.altair_chart(chart, width="stretch")
    with right:
        st.subheader("Stack Basel")
        stack = (
            alt.Chart(snapshot.basel_stack)
            .mark_bar()
            .encode(
                x=alt.X("rwa:Q", title="RWA"),
                y=alt.Y("measure:N", title=None, sort="-x"),
                color=alt.Color("measure:N", legend=None),
                tooltip=["measure", alt.Tooltip("rwa:Q", format=",.0f")],
            )
        )
        st.altair_chart(stack, width="stretch")

    st.subheader("Largest RWA contributors")
    st.subheader("RWA by sector")
    sector_chart = (
        alt.Chart(snapshot.by_sector)
        .mark_bar()
        .encode(
            x=alt.X(f"{RWA_FINAL_FIELD}:Q", title="Basel 3.1 final RWA"),
            y=alt.Y("sector:N", title=None, sort="-x"),
            color=alt.Color("sector:N", legend=None),
            tooltip=[
                "sector",
                "asset_count",
                alt.Tooltip("exposure_amount:Q", format=",.0f"),
                alt.Tooltip(f"{RWA_FINAL_FIELD}:Q", format=",.0f"),
                alt.Tooltip("rwa_density:Q", format=".2%"),
            ],
        )
    )
    st.altair_chart(sector_chart, width="stretch")

    st.dataframe(format_table(snapshot.top_assets), width="stretch", hide_index=True)


def render_regulatory_capital(capital) -> None:
    """Render aggregate Basel capital modules beyond point-in-time credit RWA."""
    st.subheader("Regulatory capital stack")
    output_floor = capital.output_floor
    leverage = capital.leverage_ratio
    operational = capital.operational_risk
    cva = capital.cva_risk

    col_pre, col_floor, col_applicable, col_leverage = st.columns(4)
    col_pre.metric("Pre-floor RWA", format_money(output_floor["pre_floor_rwa"]))
    col_floor.metric("Output floor calibration", format_pct(output_floor["floor_calibration"]))
    col_applicable.metric("Applicable RWA", format_money(output_floor["applicable_rwa"]))
    col_leverage.metric("Leverage ratio", format_pct(leverage["leverage_ratio"]))

    stack = (
        alt.Chart(capital.capital_stack)
        .mark_bar()
        .encode(
            x=alt.X("rwa:Q", title="RWA"),
            y=alt.Y("component:N", title=None, sort="-x"),
            color=alt.Color("component:N", legend=None),
            tooltip=["component", alt.Tooltip("rwa:Q", format=",.0f")],
        )
    )
    st.altair_chart(stack, width="stretch")

    left, middle, right = st.columns([1, 1, 1])
    with left:
        st.subheader("Output floor")
        st.dataframe(
            format_table(pd.DataFrame([output_floor])),
            width="stretch",
            hide_index=True,
        )
    with middle:
        st.subheader("CVA / operational risk")
        st.dataframe(
            format_table(
                pd.DataFrame(
                    [
                        {
                            "module": "CVA",
                            "capital": cva["cva_capital_requirement"],
                            "rwa": cva["cva_rwa"],
                            "approach": cva["approach_used"],
                        },
                        {
                            "module": "Operational risk",
                            "capital": operational["operational_risk_capital"],
                            "rwa": operational["operational_risk_rwa"],
                            "approach": "Standardised approach",
                        },
                    ]
                )
            ),
            width="stretch",
            hide_index=True,
        )
    with right:
        st.subheader("Leverage ratio")
        st.dataframe(
            format_table(pd.DataFrame([leverage])),
            width="stretch",
            hide_index=True,
        )

    for note in capital.methodology_notes:
        st.caption(note)


def render_runoff(projection) -> None:
    """Render closed-book run-off projection charts."""
    col_assets, col_dates, col_errors = st.columns(3)
    col_assets.metric("Run-off assets", projection.selected_asset_count)
    col_dates.metric("Projection dates", len(projection.aggregate))
    col_errors.metric("Run-off errors", len(projection.errors))

    line_frame = projection.aggregate.rename(columns=RWA_LABELS)
    measures = list(RWA_LABELS.values())
    long_frame = line_frame.melt(
        id_vars="projection_date",
        value_vars=measures,
        var_name="Measure",
        value_name="RWA",
    )
    chart = (
        alt.Chart(long_frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("projection_date:T", title="Date"),
            y=alt.Y("RWA:Q", title="RWA"),
            color=alt.Color("Measure:N"),
            tooltip=[
                alt.Tooltip("projection_date:T", title="Date"),
                "Measure",
                alt.Tooltip("RWA:Q", format=",.0f"),
            ],
        )
    )
    st.altair_chart(chart, width="stretch")

    selected_asset = st.selectbox(
        "Asset",
        projection.details.sort_values(RWA_FINAL_FIELD, ascending=False)["id"].unique(),
    )
    asset_frame = projection.details[projection.details["id"] == selected_asset].copy()
    asset_frame = asset_frame.rename(columns={RWA_FINAL_FIELD: "RWA"})
    asset_chart = (
        alt.Chart(asset_frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("projection_date:T", title="Date"),
            y=alt.Y("RWA:Q", title="Basel 3.1 final RWA"),
            tooltip=[
                alt.Tooltip("projection_date:T", title="Date"),
                "id",
                "entity_class",
                "sub_class",
                "sector",
                alt.Tooltip("RWA:Q", format=",.0f"),
            ],
        )
    )
    st.altair_chart(asset_chart, width="stretch")
    st.dataframe(format_table(asset_frame), width="stretch", hide_index=True)

    st.subheader("Run-off RWA by sector")
    sector_frame = (
        projection.details.groupby(["projection_date", "sector"], dropna=False)[RWA_FINAL_FIELD]
        .sum()
        .reset_index()
    )
    sector_chart = (
        alt.Chart(sector_frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("projection_date:T", title="Date"),
            y=alt.Y(f"{RWA_FINAL_FIELD}:Q", title="Basel 3.1 final RWA"),
            color=alt.Color("sector:N", title="Sector"),
            tooltip=[
                alt.Tooltip("projection_date:T", title="Date"),
                "sector",
                alt.Tooltip(f"{RWA_FINAL_FIELD}:Q", format=",.0f"),
            ],
        )
    )
    st.altair_chart(sector_chart, width="stretch")


def render_forecast(forecast) -> None:
    """Render scenario forecast of input variables and recalculated RWA."""
    col_assets, col_scenarios, col_dates, col_errors = st.columns(4)
    col_assets.metric("Forecast assets", forecast.selected_asset_count)
    col_scenarios.metric("Scenarios", len(forecast.scenarios))
    col_dates.metric("Forecast horizons", len(forecast.projection_dates))
    col_errors.metric("Forecast errors", len(forecast.errors))

    rwa_chart = (
        alt.Chart(forecast.aggregate)
        .mark_line(point=True)
        .encode(
            x=alt.X("projection_date:T", title="Date"),
            y=alt.Y("projected_rwa:Q", title="Projected RWA"),
            color=alt.Color("scenario_id:N", title="Scenario"),
            tooltip=[
                "scenario_id",
                "forecast_stage",
                alt.Tooltip("projection_date:T", title="Date"),
                alt.Tooltip("projected_rwa:Q", format=",.0f"),
                alt.Tooltip("rwa_delta_pct:Q", format=".2%"),
            ],
        )
    )
    st.altair_chart(rwa_chart, width="stretch")

    left, right = st.columns([1, 1])
    with left:
        exposure_chart = (
            alt.Chart(forecast.aggregate)
            .mark_line(point=True)
            .encode(
                x=alt.X("projection_date:T", title="Date"),
                y=alt.Y("forecast_exposure_amount:Q", title="Forecast exposure"),
                color=alt.Color("scenario_id:N", title="Scenario"),
                tooltip=[
                    "scenario_id",
                    alt.Tooltip("projection_date:T", title="Date"),
                    alt.Tooltip("forecast_exposure_amount:Q", format=",.0f"),
                    alt.Tooltip("exposure_delta:Q", format=",.0f"),
                ],
            )
        )
        st.altair_chart(exposure_chart, width="stretch")
    with right:
        migration_chart = (
            alt.Chart(forecast.aggregate)
            .mark_bar()
            .encode(
                x=alt.X("projection_date:T", title="Date"),
                y=alt.Y("rating_migration_count:Q", title="Rating migrations"),
                color=alt.Color("scenario_id:N", title="Scenario"),
                tooltip=[
                    "scenario_id",
                    alt.Tooltip("projection_date:T", title="Date"),
                    "rating_migration_count",
                    "matured_asset_count",
                ],
            )
        )
        st.altair_chart(migration_chart, width="stretch")

    latest_date = forecast.aggregate["projection_date"].max()
    latest = forecast.aggregate[forecast.aggregate["projection_date"] == latest_date]
    st.subheader(f"Forecast drivers at {pd.Timestamp(latest_date).date().isoformat()}")
    st.dataframe(format_table(latest), width="stretch", hide_index=True)

    scenario_id = st.selectbox("Forecast scenario", forecast.scenarios)
    available_dates = sorted(
        forecast.details.loc[forecast.details["scenario_id"] == scenario_id, "projection_date"]
        .dt.date.unique()
        .tolist()
    )
    selected_date = st.selectbox("Forecast date", available_dates)
    detail = forecast.details[
        (forecast.details["scenario_id"] == scenario_id)
        & (forecast.details["projection_date"].dt.date == selected_date)
    ]
    detail_columns = [
        "id",
        "entity_class",
        "sub_class",
        "sector",
        "current_exposure_amount",
        "forecast_exposure_amount",
        "exposure_delta",
        "current_rating",
        "forecast_rating",
        "current_dlgd",
        "forecast_dlgd",
        RWA_FINAL_FIELD,
        "rwa_density",
    ]
    st.dataframe(
        format_table(detail[detail_columns].sort_values(RWA_FINAL_FIELD, ascending=False)),
        width="stretch",
        hide_index=True,
    )


def render_monte_carlo_forecast(forecast) -> None:
    """Render VAR/LSTM Monte Carlo forecast paths and selected trajectory."""
    summary = forecast.summary
    col_assets, col_paths, col_selected, col_breach = st.columns(4)
    col_assets.metric("Forecast assets", forecast.selected_asset_count)
    col_paths.metric("Paths", int(summary["path_count"]))
    col_selected.metric("Selected path", int(summary["selected_path_id"]))
    col_breach.metric("P(breach)", format_pct(summary["breach_probability"]))

    col_rwa, col_profit, col_status = st.columns(3)
    col_rwa.metric("Selected terminal RWA", format_money(summary["selected_terminal_rwa"]))
    col_profit.metric("Selected profit", format_money(summary["selected_cumulative_profit"]))
    col_status.metric("Input status", forecast.package_status or "unknown")

    if forecast.portfolio_paths.empty:
        st.warning("Forecast returned no portfolio paths.")
        return

    path_chart = (
        alt.Chart(forecast.portfolio_paths)
        .mark_line(point=False, opacity=0.45)
        .encode(
            x=alt.X("projection_date:T", title="Date"),
            y=alt.Y("rwa:Q", title="RWA"),
            color=alt.Color("path_id:N", title="Path"),
            tooltip=[
                "path_id",
                alt.Tooltip("projection_date:T", title="Date"),
                alt.Tooltip("rwa:Q", format=",.0f"),
                alt.Tooltip("capital_ratio:Q", format=".2%"),
            ],
        )
    )
    selected_chart = (
        alt.Chart(forecast.selected_path)
        .mark_line(point=True, strokeWidth=4)
        .encode(
            x=alt.X("projection_date:T", title="Date"),
            y=alt.Y("rwa:Q", title="RWA"),
            tooltip=[
                alt.Tooltip("projection_date:T", title="Date"),
                alt.Tooltip("rwa:Q", format=",.0f"),
                alt.Tooltip("cumulative_profit:Q", format=",.0f"),
                alt.Tooltip("turnover_amount:Q", format=",.0f"),
            ],
        )
    )
    st.altair_chart(path_chart + selected_chart, width="stretch")
    selected_path_id = int(summary["selected_path_id"])

    if not forecast.sector_paths.empty:
        selected_sector_paths = forecast.sector_paths[
            forecast.sector_paths["path_id"] == selected_path_id
        ]
        sector_chart = (
            alt.Chart(selected_sector_paths)
            .mark_line(point=True)
            .encode(
                x=alt.X("projection_date:T", title="Projection date"),
                y=alt.Y("rwa:Q", title="RWA"),
                color=alt.Color("sector:N", title="Sector"),
                tooltip=[
                    "sector",
                    "asset_count",
                    alt.Tooltip("projection_date:T", title="Projection date"),
                    alt.Tooltip("rwa:Q", format=",.0f"),
                    alt.Tooltip("exposure_amount:Q", format=",.0f"),
                ],
            )
        )
        st.subheader("Selected path by sector")
        st.altair_chart(sector_chart, width="stretch")

    selected_market = forecast.market_paths[forecast.market_paths["path_id"] == selected_path_id]
    factor_columns = [
        "volatility_index",
        "credit_spread_bps",
        "liquidity_index",
        "default_probability_proxy",
        "loss_probability_proxy",
    ]
    factors = selected_market[["projection_date", *factor_columns]].melt(
        id_vars="projection_date",
        var_name="Factor",
        value_name="Value",
    )
    factor_chart = (
        alt.Chart(factors)
        .mark_line(point=True)
        .encode(
            x=alt.X("projection_date:T", title="Date"),
            y=alt.Y("Value:Q", title="Value"),
            color=alt.Color("Factor:N"),
            tooltip=[
                "Factor",
                alt.Tooltip("projection_date:T", title="Date"),
                alt.Tooltip("Value:Q", format=",.4f"),
            ],
        )
    )
    st.altair_chart(factor_chart, width="stretch")

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Top path scores")
        st.dataframe(format_table(forecast.path_scores), width="stretch", hide_index=True)
    with right:
        st.subheader("Selected path")
        st.dataframe(
            format_table(forecast.selected_path),
            width="stretch",
            hide_index=True,
        )


def render_rats(rats) -> None:
    """Render Risk-Aware Trading Swarm optimization output."""
    summary = rats.summary
    col_assets, col_status, col_feasible, col_legs = st.columns(4)
    col_assets.metric("RATS assets", rats.selected_asset_count)
    col_status.metric("Input status", rats.package_status or "unknown")
    col_feasible.metric("Feasible", "yes" if summary["feasible"] else "no")
    col_legs.metric("Selected legs", int(summary["selected_legs"]))

    col_before, col_after, col_saving, col_cost = st.columns(4)
    col_before.metric(
        "Projected RWA before",
        format_money(summary["projected_rwa_before_strategy"]),
    )
    col_after.metric("Optimized RWA", format_money(summary["optimized_projected_rwa"]))
    col_saving.metric("RWA saving", format_money(summary["rwa_saving"]))
    col_cost.metric("Business cost", format_money(summary["total_business_cost"]))

    comparison = pd.DataFrame(
        [
            {
                "Stage": "Projected before strategy",
                "RWA": summary["projected_rwa_before_strategy"],
            },
            {
                "Stage": "Optimized projected RWA",
                "RWA": summary["optimized_projected_rwa"],
            },
        ]
    )
    comparison_chart = (
        alt.Chart(comparison)
        .mark_bar()
        .encode(
            x=alt.X("RWA:Q", title="RWA"),
            y=alt.Y("Stage:N", title=None, sort="-x"),
            color=alt.Color("Stage:N", legend=None),
            tooltip=["Stage", alt.Tooltip("RWA:Q", format=",.0f")],
        )
    )
    st.altair_chart(comparison_chart, width="stretch")

    if not rats.convergence.empty:
        convergence_chart = (
            alt.Chart(rats.convergence)
            .mark_line(point=True)
            .encode(
                x=alt.X("iteration:O", title="Iteration"),
                y=alt.Y("global_best_objective:Q", title="Objective"),
                tooltip=[
                    "iteration",
                    alt.Tooltip("global_best_objective:Q", format=",.0f"),
                    alt.Tooltip("global_best_rwa_saving:Q", format=",.0f"),
                    alt.Tooltip("feasible_particle_ratio:Q", format=".2%"),
                ],
            )
        )
        st.altair_chart(convergence_chart, width="stretch")

    if summary["constraint_violations"]:
        st.warning(", ".join(summary["constraint_violations"]))

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Best strategy")
        st.dataframe(format_table(rats.best_strategy), width="stretch", hide_index=True)
    with right:
        st.subheader("Top UEI candidates")
        st.dataframe(format_table(rats.candidates), width="stretch", hide_index=True)


def render_steering(steering) -> None:
    """Render scenario summaries, attribution and recommended steering actions."""
    total_saving = (
        float(steering.recommendations["estimated_rwa_saving"].sum())
        if "estimated_rwa_saving" in steering.recommendations.columns
        else 0.0
    )
    col_assets, col_dates, col_status, col_saving = st.columns(4)
    col_assets.metric("Optimization assets", steering.selected_asset_count)
    col_dates.metric("Projection dates", len(steering.projection_dates))
    col_status.metric("Input status", steering.package_status or "unknown")
    col_saving.metric("Estimated RWA saving", format_money(total_saving))

    scenario_chart = (
        alt.Chart(steering.summaries)
        .mark_line(point=True)
        .encode(
            x=alt.X("projection_date:T", title="Date"),
            y=alt.Y("projected_rwa:Q", title="Projected RWA"),
            color=alt.Color("scenario_id:N", title="Scenario"),
            tooltip=[
                "scenario_id",
                "regime_label",
                alt.Tooltip("projection_date:T", title="Date"),
                alt.Tooltip("projected_rwa:Q", format=",.0f"),
                alt.Tooltip("rwa_delta_pct:Q", format=".2%"),
            ],
        )
    )
    st.altair_chart(scenario_chart, width="stretch")

    latest_date = steering.attributions["projection_date"].max()
    attribution = steering.attributions[steering.attributions["projection_date"] == latest_date]
    delta_columns = [
        "volume_delta",
        "maturity_delta",
        "rating_delta",
        "dlgd_delta",
        "fx_delta",
        "regulatory_delta",
        "interaction_or_residual_delta",
    ]
    attribution_long = attribution.melt(
        id_vars=["scenario_id"],
        value_vars=delta_columns,
        var_name="Driver",
        value_name="RWA delta",
    )
    attribution_chart = (
        alt.Chart(attribution_long)
        .mark_bar()
        .encode(
            x=alt.X("Driver:N", title=None),
            y=alt.Y("RWA delta:Q", title="RWA delta"),
            color=alt.Color("scenario_id:N", title="Scenario"),
            column=alt.Column("scenario_id:N", title=None),
            tooltip=["scenario_id", "Driver", alt.Tooltip("RWA delta:Q", format=",.0f")],
        )
    )
    st.subheader(f"Attribution at {pd.Timestamp(latest_date).date().isoformat()}")
    st.altair_chart(attribution_chart, width="stretch")

    st.subheader("Recommended actions")
    if steering.recommendations.empty:
        st.info("No recommendations were returned for the selected portfolio and scenarios.")
        return

    product_savings = (
        steering.recommendations.groupby(["sub_class", "recommended_action"], dropna=False)
        .agg(estimated_rwa_saving=("estimated_rwa_saving", "sum"))
        .reset_index()
        .sort_values("estimated_rwa_saving", ascending=False)
    )
    savings_chart = (
        alt.Chart(product_savings)
        .mark_bar()
        .encode(
            x=alt.X("estimated_rwa_saving:Q", title="Estimated RWA saving"),
            y=alt.Y("sub_class:N", title="Product / sub-class", sort="-x"),
            color=alt.Color("recommended_action:N", title="Action"),
            tooltip=[
                "sub_class",
                "recommended_action",
                alt.Tooltip("estimated_rwa_saving:Q", format=",.0f"),
            ],
        )
    )
    st.altair_chart(savings_chart, width="stretch")
    st.dataframe(format_table(steering.recommendations), width="stretch", hide_index=True)


def render_ai_executive_commentary(snapshot, as_of_date: date, runs):
    """Render the AI Executive Commentary component backed by the LangGraph workflow."""
    state_key = f"ai_commentary::{as_of_date.isoformat()}::{runs.scenario_id}"
    if state_key not in st.session_state:
        with st.spinner("Generating AI executive commentary..."):
            st.session_state[state_key] = generate_ai_commentary_state(
                snapshot,
                as_of_date,
                runs.scenario_id,
            )

    header, action = st.columns([0.72, 0.28])
    header.markdown(
        """
        <div class="ai-commentary-title">
            <h4>AI Executive Commentary</h4>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if action.button("Regenerate", key=f"{state_key}::regenerate"):
        with st.spinner("Regenerating AI executive commentary..."):
            st.session_state[state_key] = generate_ai_commentary_state(
                snapshot,
                as_of_date,
                runs.scenario_id,
            )

    commentary_state = st.session_state.get(state_key, {})
    error = commentary_state.get("error")
    if error:
        st.error("AI Executive Commentary is unavailable. No substitute commentary was displayed.")
        st.caption(str(error))
        return None

    response = commentary_state.get("response")
    if response is None:
        st.info("AI Executive Commentary is not available for the selected inputs.")
        return None
    if response.status == "BLOCKED":
        st.warning("AI Executive Commentary was blocked by guardrail policy and is unavailable.")
        st.caption(
            f"Guardrail blocks: {response.observability.guardrail_block_count}; "
            f"source {response.final_commentary.source_label}."
        )
        return response

    commentary = response.final_commentary
    executive_tab, cro_tab, cfo_tab = st.tabs(["Executive Summary", "CRO View", "CFO View"])
    with executive_tab:
        render_commentary_view(
            narrative=commentary.executive_summary,
            observations=[
                *commentary.data_quality_observations,
                *commentary.quantitative_validation,
            ],
            actions=commentary.recommended_actions,
            generated_at=commentary.generated_at,
            source_label=commentary.source_label,
        )
    with cro_tab:
        render_commentary_view(
            narrative=commentary.cro_view,
            observations=[*commentary.risk_observations, *commentary.quantitative_validation],
            actions=commentary.recommended_actions,
            generated_at=commentary.generated_at,
            source_label=commentary.source_label,
        )
    with cfo_tab:
        render_commentary_view(
            narrative=commentary.cfo_view,
            observations=commentary.quantitative_validation,
            actions=commentary.recommended_actions,
            generated_at=commentary.generated_at,
            source_label=commentary.source_label,
        )
    st.caption(
        f"Workflow {response.graph_backend}; checkpointer "
        f"{response.observability.checkpointer}; source {commentary.source_label}."
    )
    return response


def generate_ai_commentary_state(snapshot, as_of_date: date, scenario_id: str) -> dict[str, Any]:
    """Generate commentary state for Streamlit, preserving unavailable/error outcomes."""
    try:
        request = build_rwa_commentary_request(
            snapshot,
            request_id=f"dashboard-{as_of_date.isoformat()}-{scenario_id}",
            scenario_id=scenario_id,
        )
        return {
            "response": asyncio.run(RwaAgentService().run_multi_agent_analysis(request)),
            "error": None,
        }
    except Exception as exc:
        return {"response": None, "error": f"{type(exc).__name__}: {exc}"}


def build_rwa_commentary_request(
    snapshot,
    *,
    request_id: str,
    scenario_id: str,
) -> MultiAgentRwaAnalysisRequest:
    """Build an anonymized RWA commentary request from calculator output rows."""
    input_data: list[dict[str, Any]] = []
    output_results: list[dict[str, Any]] = []
    for row in snapshot.results.to_dict(orient="records"):
        asset_id = str(row["id"])
        exposure_amount = decimal_text(row.get("exposure_amount"), default="0")
        risk_weight = decimal_text(row.get(RWA_FINAL_RISK_WEIGHT_FIELD))
        input_data.append(
            {
                "asset_id": asset_id,
                "asset_class": text_or_default(row.get("entity_class"), "Unclassified"),
                "sector": text_or_default(row.get("sector"), "Unclassified"),
                "exposure_amount": exposure_amount,
                "risk_weight": risk_weight,
                "rating": text_or_none(row.get("counterparty_credit_quality_grade")),
                "validation_status": "PASSED",
                "pd": decimal_text(row.get("basel_3_1_pd")),
                "lgd": decimal_text(row.get("basel_3_1_dlgd")),
                "maturity_years": decimal_text(row.get("residual_maturity")),
            }
        )
        output_results.append(
            {
                "asset_id": asset_id,
                "rwa_amount": decimal_text(row.get(RWA_FINAL_FIELD), default="0"),
                "exposure_amount": exposure_amount,
                "risk_weight": risk_weight,
                "sector": text_or_default(row.get("sector"), "Unclassified"),
                "rating": text_or_none(row.get("counterparty_credit_quality_grade")),
                "risk_class": text_or_default(row.get("entity_class"), "Unclassified"),
                "approach": "Basel 3.1 final",
            }
        )
    return MultiAgentRwaAnalysisRequest(
        request_id=request_id,
        rwa_input_data=input_data,
        rwa_output_results=output_results,
        loop_limit=3,
    )


def render_commentary_view(
    *,
    narrative: str,
    observations: list[str],
    actions: list[str],
    generated_at,
    source_label: str,
) -> None:
    """Render one tab of the AI Executive Commentary component."""
    observation_items = "".join(f"<li>{html.escape(item)}</li>" for item in observations if item)
    checklist = "".join(
        (
            '<div class="commentary-check">'
            '<span class="commentary-checkmark">&#10003;</span>'
            f"<span>{html.escape(action)}</span>"
            "</div>"
        )
        for action in actions
    )
    generated_label = generated_at.strftime("%Y-%m-%d %H:%M:%S %Z")
    st.markdown(
        f"""
        <div class="ai-commentary-shell">
            <p class="ai-commentary-copy">{html.escape(narrative)}</p>
            <p><strong>Supporting observations</strong></p>
            <ul>{observation_items or "<li>No open observations for this view.</li>"}</ul>
            <p><strong>Recommended actions</strong></p>
            <div class="commentary-checklist">
                {checklist or '<div class="commentary-check">No recommended actions.</div>'}
            </div>
            <div class="ai-commentary-meta">
                Generated {html.escape(generated_label)} by {html.escape(source_label)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def decimal_text(value: object, *, default: str | None = None) -> str | None:
    """Return a string decimal for Pydantic request validation."""
    if value is None or pd.isna(value):
        return default
    return str(value)


def text_or_none(value: object) -> str | None:
    """Return sanitized optional text for anonymized commentary input."""
    if value is None or pd.isna(value):
        return None
    return str(value)


def text_or_default(value: object, default: str) -> str:
    """Return sanitized text with a stable default."""
    return text_or_none(value) or default


def render_agent_briefing(snapshot, capital, overview, as_of_date: date, runs) -> None:
    """Render the agent-ready management briefing workspace from calculated data."""
    agent_context = AgentRuntimeContext(
        as_of_date=as_of_date,
        scenario_id=runs.scenario_id,
        snapshot=snapshot,
        capital=capital,
        overview=overview,
        runs=runs,
    )
    evidence_response = RwaAgentService().evidence_from_context(
        BriefingRequest(
            as_of_date=as_of_date,
            scenario_id=runs.scenario_id,
        ),
        agent_context,
    )
    output_floor = capital.output_floor
    quality_summary = overview.data_quality_summary.copy()
    blocking_issues = (
        int(quality_summary.loc[quality_summary["is_blocking"], "count"].sum())
        if not quality_summary.empty
        else 0
    )
    quality_issues = int(overview.data_quality_flags.shape[0])
    generated_files = len(overview.manifest["generated_files"])

    st.markdown(
        f"""
        <div class="briefing-card">
            <h4>5. RWA Intelligence Briefing</h4>
            <p>
                Agent graph for reporting date {as_of_date.isoformat()}.
                The visible commentary is generated from prepared input files,
                calculator outputs, capital modules and the complete model run set.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_total, col_cet1, col_capital, col_quality, col_confidence = st.columns(5)
    col_total.metric("Total RWA current", format_money(output_floor["applicable_rwa"]))
    col_cet1.metric("CET1 ratio", format_pct(output_floor["cet1_ratio"]))
    col_capital.metric("Total capital ratio", format_pct(output_floor["total_capital_ratio"]))
    col_quality.metric("Quality findings", quality_issues, delta=f"{blocking_issues} blocking")
    col_confidence.metric("Prepared files", generated_files)

    left, right = st.columns([1.08, 1])
    with left:
        st.subheader("Model movement attribution")
        entity_frame = runs.model_summary.sort_values("projected_rwa", ascending=False).copy()
        entity_chart = (
            alt.Chart(entity_frame)
            .mark_bar()
            .encode(
                x=alt.X("rwa_delta:Q", title="RWA delta"),
                y=alt.Y("model:N", title=None, sort="-x"),
                color=alt.Color("scenario_id:N", title="Scenario"),
                tooltip=[
                    "model",
                    "scenario_id",
                    alt.Tooltip("projection_date:T", title="Projection date"),
                    alt.Tooltip("baseline_rwa:Q", format=",.0f"),
                    alt.Tooltip("projected_rwa:Q", format=",.0f"),
                    alt.Tooltip("rwa_delta:Q", format=",.0f"),
                ],
            )
        )
        st.altair_chart(entity_chart, width="stretch")
        st.dataframe(format_table(entity_frame), width="stretch", hide_index=True)

    with right:
        analysis_response = render_ai_executive_commentary(snapshot, as_of_date, runs)

    lower_left, lower_right = st.columns([1, 1.08])
    with lower_left:
        st.subheader("Data quality findings")
        st.dataframe(format_table(quality_summary), width="stretch", hide_index=True)
    with lower_right:
        st.subheader("Agent workspace")
        st.markdown(
            agent_slot_cards(snapshot, capital, overview, runs, analysis_response),
            unsafe_allow_html=True,
        )
        st.subheader("Capital briefing context")
        st.dataframe(format_table(capital.capital_stack), width="stretch", hide_index=True)

    st.subheader("Evidence & traceability")
    st.markdown(evidence_trace_strip(snapshot, capital, overview, runs), unsafe_allow_html=True)
    evidence_frame = pd.DataFrame(
        [item.model_dump(mode="python") for item in evidence_response.evidence_inventory]
    )
    st.dataframe(
        format_table(evidence_frame),
        width="stretch",
        hide_index=True,
    )
    for note in capital.methodology_notes:
        st.caption(note)


def agent_slot_cards(snapshot, capital, overview, runs, agent_response=None) -> str:
    """Return HTML cards for the agent registry slots."""
    if agent_response is not None and hasattr(agent_response, "messages"):
        latest_messages = {}
        for message in agent_response.messages:
            latest_messages[message.agent_name] = message
        cards = [
            (
                '<div class="agent-card">'
                f"<h4>{html.escape(str(agent_name))}</h4>"
                f"<p>{html.escape(message.content)}</p>"
                f'<span class="agent-status">Completed</span>'
                "</div>"
            )
            for agent_name, message in latest_messages.items()
        ]
        return f'<div class="agent-grid">{"".join(cards)}</div>'

    if agent_response is not None and hasattr(agent_response, "agent_results"):
        cards = [
            (
                '<div class="agent-card">'
                f"<h4>{html.escape(result.agent_name)}</h4>"
                f"<p>{html.escape(result.summary)}</p>"
                f'<span class="agent-status">{result.status.title()}</span>'
                "</div>"
            )
            for result in agent_response.agent_results
        ]
        return f'<div class="agent-grid">{"".join(cards)}</div>'

    validation_status = overview.manifest["validation_status"]
    hash_count = len(overview.manifest.get("file_sha256", {}))
    source_count = len(overview.manifest.get("source_files", []))
    quality_issues = int(overview.data_quality_flags.shape[0])
    slots = [
        {
            "name": AGENT_SLOT_NAMES[0],
            "body": (
                f"{runs.model_summary['model'].nunique()} calculated model outputs, "
                f"{len(runs.projection_comparison)} projection points and movement deltas."
            ),
            "status": "Slot ready",
            "class": "",
        },
        {
            "name": AGENT_SLOT_NAMES[1],
            "body": (
                f"{len(capital.capital_stack)} capital modules, CVA, operational risk, "
                "output floor and leverage ratio context."
            ),
            "status": "Slot ready",
            "class": "",
        },
        {
            "name": AGENT_SLOT_NAMES[2],
            "body": (
                f"{quality_issues} prepared data-quality findings; package {validation_status}."
            ),
            "status": "Slot ready",
            "class": "",
        },
        {
            "name": AGENT_SLOT_NAMES[3],
            "body": f"{hash_count} file hashes and {source_count} source-file references.",
            "status": "Slot ready",
            "class": "",
        },
        {
            "name": AGENT_SLOT_NAMES[4],
            "body": (
                f"Board commentary input contract includes {len(capital.capital_stack)} "
                f"capital components and {len(runs.sector_projection)} sector rows."
            ),
            "status": "Input ready",
            "class": "",
        },
    ]
    cards = [
        (
            '<div class="agent-card">'
            f"<h4>{slot['name']}</h4>"
            f"<p>{slot['body']}</p>"
            f'<span class="agent-status{slot["class"]}">{slot["status"]}</span>'
            "</div>"
        )
        for slot in slots
    ]
    return f'<div class="agent-grid">{"".join(cards)}</div>'


def lineage_frame(snapshot, capital, overview, runs) -> pd.DataFrame:
    """Build a page-ready lineage table from calculated objects and package metadata."""
    generated_files = len(overview.manifest["generated_files"])
    hashes = len(overview.manifest.get("file_sha256", {}))
    return pd.DataFrame(
        [
            {
                "source": "Prepared exposure file",
                "target": "RWA calculator",
                "artifact_type": "CSV input",
                "records": int(snapshot.summary["input_data_records"]),
                "status": "CALCULATED",
            },
            {
                "source": "Generated input package",
                "target": "Forecast, steering and optimizer services",
                "artifact_type": "Generated CSV package",
                "records": generated_files,
                "status": overview.manifest["validation_status"],
            },
            {
                "source": "RWA calculator",
                "target": "Current dashboard",
                "artifact_type": "Calculator output rows",
                "records": int(snapshot.results.shape[0]),
                "status": "CALCULATED",
            },
            {
                "source": "Model run set",
                "target": "Scenario analysis",
                "artifact_type": "Projection frame",
                "records": int(runs.projection_comparison.shape[0]),
                "status": "CALCULATED",
            },
            {
                "source": "Model run set",
                "target": "Sector projection dashboard",
                "artifact_type": "Sector projection frame",
                "records": int(runs.sector_projection.shape[0]),
                "status": "CALCULATED",
            },
            {
                "source": "Capital generated inputs",
                "target": "Regulatory capital stack",
                "artifact_type": "Capital module output",
                "records": int(capital.capital_stack.shape[0]),
                "status": "CALCULATED",
            },
            {
                "source": "Manifest hashes",
                "target": "Reports & Evidence",
                "artifact_type": "SHA-256 evidence",
                "records": hashes,
                "status": overview.manifest["validation_status"],
            },
        ]
    )


def evidence_trace_strip(snapshot, capital, overview, runs) -> str:
    """Return concept-style traceability cards for the briefing footer."""
    file_hashes = overview.manifest.get("file_sha256", {})
    generated_files = len(overview.manifest["generated_files"])
    quality_gates = len(overview.validation_report["quality_gates"])
    validation_status = overview.manifest["validation_status"]
    input_records = snapshot.summary["input_data_records"]
    cards = [
        {
            "title": "Calculation context",
            "body": f"{input_records} rows, as-of {snapshot.as_of_date.isoformat()}",
        },
        {
            "title": "Prepared inputs",
            "body": f"{generated_files} generated files, {len(file_hashes)} hashes",
        },
        {
            "title": "Applied modules",
            "body": ", ".join(capital.capital_stack["component"].tolist()),
        },
        {
            "title": "Model outputs",
            "body": (
                f"{runs.model_summary['model'].nunique()} models, "
                f"{len(runs.projection_comparison)} projection rows"
            ),
        },
        {
            "title": "Validation gates",
            "body": f"{quality_gates} gates, {validation_status}",
        },
    ]
    html_cards = [
        (f'<div class="trace-card"><h4>{card["title"]}</h4><p>{card["body"]}</p></div>')
        for card in cards
    ]
    return f'<div class="evidence-strip">{"".join(html_cards)}</div>'


def render_input_package(overview) -> None:
    """Render generated-input manifest and data-quality diagnostics."""
    col_version, col_status, col_seed, col_files = st.columns(4)
    col_version.metric("Version", display_version(overview.manifest["version_id"]))
    col_status.metric("Validation", overview.manifest["validation_status"])
    col_seed.metric("Seed", overview.manifest["random_seed"])
    col_files.metric("Files", len(overview.manifest["generated_files"]))

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Generated files")
        st.dataframe(overview.row_counts, width="stretch", hide_index=True)
    with right:
        st.subheader("Quality flags")
        st.dataframe(overview.data_quality_summary, width="stretch", hide_index=True)

    st.subheader("Quality gates")
    gates = pd.DataFrame({"quality_gate": overview.validation_report["quality_gates"]})
    st.dataframe(gates, width="stretch", hide_index=True)


def format_money(value: float | int | None) -> str:
    """Format large money-like dashboard values in millions."""
    if value is None:
        return "n/a"
    return f"{float(value) / 1_000_000:,.1f}m"


def format_pct(value: float | int | None) -> str:
    """Format percentage dashboard values."""
    if value is None:
        return "n/a"
    return f"{float(value):.2%}"


def format_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a rounded copy of a DataFrame for readable dashboard tables."""
    display = frame.copy()
    for column in display.select_dtypes(include=["float", "float64"]).columns:
        display[column] = display[column].round(4)
    return display


def display_version(value: str | None) -> str:
    """Return an enterprise-safe version label for UI surfaces."""
    if not value:
        return "n/a"
    return str(value)


if __name__ == "__main__":
    main()
