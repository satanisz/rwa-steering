from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from rwa_dashboard.data import (
    RWA_FINAL_FIELD,
    RWA_FOUNDATION_FIELD,
    RWA_STANDARDISED_FIELD,
    current_rwa_snapshot,
    default_as_of_date,
    input_package_overview,
    regulatory_capital_snapshot,
    runoff_projection,
)

RWA_LABELS = {
    "basel_3_0_rwa": "Basel 3.0",
    RWA_FOUNDATION_FIELD: "Basel 3.1 foundation",
    RWA_STANDARDISED_FIELD: "Basel 3.1 standardised",
    RWA_FINAL_FIELD: "Basel 3.1 row-level RWA",
}
MODEL_RUNOFF = "Run-off f(x,t)"
RUNOFF_METHODOLOGY_LABEL = MODEL_RUNOFF
RUNOFF_METHODOLOGY_OPTIONS = (MODEL_RUNOFF,)
CET1_MINIMUM_DASHBOARD_REQUIREMENT = 0.105

DASHBOARD_DARK_CSS = """
<style>
    .stApp {
        background:
            radial-gradient(circle at 78% 0%, rgba(13, 83, 145, 0.28), transparent 30rem),
            radial-gradient(circle at 8% 8%, rgba(28, 84, 180, 0.20), transparent 24rem),
            #050d1b;
        color: #eef5ff;
    }
    [data-testid="stHeader"] {
        background: transparent;
    }
    [data-testid="stAppViewContainer"] > .main {
        background: transparent;
    }
    .block-container {
        max-width: 1440px;
        padding-top: 1.25rem;
        padding-bottom: 2.5rem;
    }
    section[data-testid="stSidebar"] {
        background: #06111f;
        border-right: 1px solid rgba(104, 137, 188, 0.26);
    }
    section[data-testid="stSidebar"] * {
        color: #d9e6f7;
    }
    .dashboard-sidebar-mark {
        display: grid;
        gap: 0.75rem;
        padding: 0.35rem 0 1.1rem;
    }
    .dashboard-nav-item {
        border: 1px solid rgba(124, 166, 237, 0.24);
        border-radius: 8px;
        padding: 0.72rem 0.8rem;
        background: rgba(8, 22, 42, 0.72);
        color: #dce9fb;
        font-weight: 700;
        letter-spacing: 0;
        text-align: center;
    }
    .dashboard-nav-item.active {
        background: linear-gradient(135deg, #0a4ad6, #0c2d76);
        border-color: rgba(89, 152, 255, 0.60);
        box-shadow: 0 14px 34px rgba(18, 87, 210, 0.30);
    }
    .dashboard-title-wrap {
        border: 1px solid rgba(90, 131, 190, 0.28);
        border-radius: 22px;
        background: linear-gradient(140deg, rgba(6, 18, 34, 0.94), rgba(3, 13, 27, 0.88));
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.34);
        padding: 2rem 2rem 1.35rem;
        margin-bottom: 1rem;
    }
    .dashboard-eyebrow {
        color: #72a7ff;
        font-size: 0.82rem;
        font-weight: 800;
        letter-spacing: 0;
        margin-bottom: 0.35rem;
        text-transform: uppercase;
    }
    .dashboard-title-wrap h1 {
        color: #f8fbff;
        font-size: 2rem;
        line-height: 1.1;
        margin: 0;
        letter-spacing: 0;
    }
    .dashboard-title-wrap p {
        color: #aebbd0;
        font-size: 1rem;
        margin: 0.5rem 0 0;
    }
    .dashboard-kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 1rem;
        margin: 1rem 0 1.35rem;
    }
    .dashboard-kpi-card {
        min-height: 132px;
        border: 1px solid rgba(86, 126, 183, 0.30);
        border-radius: 8px;
        background: linear-gradient(145deg, rgba(7, 20, 38, 0.96), rgba(4, 14, 29, 0.92));
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
        padding: 1.35rem 1.45rem;
        display: grid;
        grid-template-columns: 58px 1fr;
        column-gap: 1rem;
        align-items: center;
    }
    .dashboard-kpi-icon {
        align-items: center;
        border-radius: 8px;
        display: flex;
        font-size: 0.9rem;
        font-weight: 900;
        height: 58px;
        justify-content: center;
        letter-spacing: 0;
        width: 58px;
    }
    .dashboard-kpi-card.blue .dashboard-kpi-icon {
        background: rgba(18, 98, 255, 0.18);
        color: #1f7cff;
    }
    .dashboard-kpi-card.violet .dashboard-kpi-icon {
        background: rgba(122, 85, 255, 0.18);
        color: #8b6dff;
    }
    .dashboard-kpi-card.green .dashboard-kpi-icon {
        background: rgba(22, 199, 120, 0.16);
        color: #2bd27f;
    }
    .dashboard-kpi-card.amber .dashboard-kpi-icon {
        background: rgba(245, 176, 33, 0.18);
        color: #ffc83d;
    }
    .dashboard-kpi-label {
        color: #cbd7e7;
        font-size: 0.96rem;
        font-weight: 700;
        margin-bottom: 0.4rem;
    }
    .dashboard-kpi-value {
        color: #f8fbff;
        font-size: 1.75rem;
        font-weight: 850;
        line-height: 1;
    }
    .dashboard-kpi-value.negative {
        color: #ff4f55;
    }
    .dashboard-kpi-value.positive {
        color: #2bd27f;
    }
    .dashboard-kpi-sub {
        color: #8fa4be;
        font-size: 0.82rem;
        margin-top: 0.35rem;
    }
    div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stAltairChart"]),
    div[data-testid="stDataFrame"] {
        border-radius: 8px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(8, 22, 42, 0.86);
        border: 1px solid rgba(86, 126, 183, 0.28);
        border-radius: 8px;
        color: #cad7e8;
        height: 42px;
        padding: 0 1rem;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(20, 80, 190, 0.32);
        border-color: rgba(105, 163, 255, 0.56);
        color: #ffffff;
    }
    h2, h3 {
        color: #eff6ff;
        letter-spacing: 0;
    }
    [data-testid="stMetric"] {
        background: rgba(7, 20, 38, 0.82);
        border: 1px solid rgba(86, 126, 183, 0.26);
        border-radius: 8px;
        padding: 0.9rem 1rem;
    }
    [data-testid="stMetricValue"] {
        color: #f8fbff;
    }
    [data-testid="stMetricLabel"] {
        color: #aebbd0;
    }
    @media (max-width: 1100px) {
        .dashboard-kpi-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }
    @media (max-width: 700px) {
        .dashboard-kpi-grid {
            grid-template-columns: 1fr;
        }
        .dashboard-title-wrap {
            padding: 1.35rem;
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
def cached_regulatory_capital(as_of_date: date):
    """Cache portfolio-level Basel capital module output across Streamlit reruns."""
    return regulatory_capital_snapshot(as_of_date)


@st.cache_data(ttl=600, show_spinner=False)
def cached_input_package():
    """Cache generated-input metadata across Streamlit reruns."""
    return input_package_overview()


def main() -> None:
    """Render the RWA run-off dashboard."""
    st.set_page_config(page_title="RWA Application", layout="wide")
    apply_dashboard_theme()

    default_date = default_as_of_date()
    render_dashboard_sidebar()
    st.sidebar.title("Parametry")
    as_of_date = st.sidebar.date_input("Dzien kalkulacji", value=default_date)
    selected_methodology = methodology_selector()
    snapshot = cached_current(as_of_date)
    capital = cached_regulatory_capital(as_of_date)
    overview = cached_input_package()

    render_dashboard_header(as_of_date)

    tab_current, tab_model, tab_data = st.tabs(
        ["Dashboard", "Run-off methodology", "Dane i jakosc"]
    )

    with tab_current:
        overview_runoff = cached_runoff_projection(as_of_date, 12, 100)
        render_dashboard_overview(snapshot, capital, overview, overview_runoff)
        render_current(snapshot)
        render_regulatory_capital(capital)

    with tab_model:
        render_runoff_methodology(selected_methodology, as_of_date)

    with tab_data:
        render_input_package(overview)


def apply_dashboard_theme() -> None:
    """Inject the dark cockpit styling for the Streamlit shell."""
    st.markdown(DASHBOARD_DARK_CSS, unsafe_allow_html=True)


def render_dashboard_sidebar() -> None:
    """Render the compact navigation rail motif in the sidebar."""
    st.sidebar.markdown(
        """
        <div class="dashboard-sidebar-mark">
            <div class="dashboard-nav-item active">RWA</div>
            <div class="dashboard-nav-item">CAP</div>
            <div class="dashboard-nav-item">RUN</div>
            <div class="dashboard-nav-item">DQ</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_header(as_of_date: date) -> None:
    """Render the dashboard header in the requested visual direction."""
    st.markdown(
        f"""
        <div class="dashboard-title-wrap">
            <div class="dashboard-eyebrow">RWA monitoring</div>
            <h1>RWA Application</h1>
            <p>Risk-Weighted Assets Dashboard | as-of {as_of_date.isoformat()}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_overview(snapshot, capital, overview, runoff) -> None:
    """Render the first-screen dashboard cockpit from prepared calculation outputs."""
    output_floor = capital.output_floor
    cet1_impact = output_floor["cet1_ratio"] - output_floor["cet1_ratio_pre_floor"]
    capital_buffer = output_floor["cet1_ratio"] - CET1_MINIMUM_DASHBOARD_REQUIREMENT
    quality_score = data_quality_score(snapshot, overview)

    render_dashboard_kpis(
        (
            {
                "tone": "blue",
                "icon": "RWA",
                "label": "Total RWA",
                "value": format_full_money(output_floor["applicable_rwa"]),
                "value_class": "",
                "sub": "PLN applicable RWA",
            },
            {
                "tone": "violet",
                "icon": "C1",
                "label": "CET1 Ratio Impact",
                "value": format_pp(cet1_impact),
                "value_class": "negative" if cet1_impact < 0 else "positive",
                "sub": "vs pre-floor ratio",
            },
            {
                "tone": "green",
                "icon": "BF",
                "label": "Capital Buffer",
                "value": format_pp(capital_buffer),
                "value_class": "positive" if capital_buffer >= 0 else "negative",
                "sub": "CET1 vs 10.5% dashboard threshold",
            },
            {
                "tone": "amber",
                "icon": "DQ",
                "label": "Data Quality Score",
                "value": format_pct(quality_score),
                "value_class": "positive"
                if quality_score is not None and quality_score >= 0.95
                else "",
                "sub": f"{len(overview.data_quality_flags):,} flags in prepared package",
            },
        )
    )

    movement = runoff_waterfall_frame(runoff)
    left, right = st.columns([1.45, 1])
    with left:
        st.subheader("RWA Movement Attribution (Run-off)")
        st.altair_chart(runoff_waterfall_chart(movement), width="stretch")
    with right:
        st.subheader("Run-off drivers")
        st.dataframe(runoff_driver_table(movement), width="stretch", hide_index=True)


def render_dashboard_kpis(cards: tuple[dict[str, str], ...]) -> None:
    """Render KPI cards as a single responsive dark grid."""
    card_html = "\n".join(
        f"""
        <div class="dashboard-kpi-card {card["tone"]}">
            <div class="dashboard-kpi-icon">{card["icon"]}</div>
            <div>
                <div class="dashboard-kpi-label">{card["label"]}</div>
                <div class="dashboard-kpi-value {card["value_class"]}">{card["value"]}</div>
                <div class="dashboard-kpi-sub">{card["sub"]}</div>
            </div>
        </div>
        """
        for card in cards
    )
    st.markdown(
        f"""<div class="dashboard-kpi-grid">{card_html}</div>""",
        unsafe_allow_html=True,
    )


def data_quality_score(snapshot, overview) -> float | None:
    """Score prepared data by successful records less package quality flags."""
    record_count = float(snapshot.summary.get("input_data_records", 0) or 0)
    if record_count <= 0:
        return None
    flagged_rows = float(len(overview.data_quality_flags))
    return max(0.0, min(1.0, 1.0 - flagged_rows / record_count))


def runoff_waterfall_frame(projection) -> pd.DataFrame:
    """Build waterfall rows from the actual run-off aggregate projection."""
    aggregate = projection.aggregate.sort_values("projection_date").reset_index(drop=True)
    if aggregate.empty:
        return pd.DataFrame(
            columns=[
                "driver",
                "impact",
                "start",
                "end",
                "kind",
                "sort",
                "start_m",
                "end_m",
                "label_y",
                "chart_label",
            ]
        )

    values = aggregate[RWA_FINAL_FIELD].astype(float)
    opening = float(values.iloc[0])
    rows = [
        {
            "driver": "Opening RWA",
            "impact": opening,
            "start": 0.0,
            "end": opening,
            "kind": "opening",
            "sort": 0,
        }
    ]

    previous = opening
    for index in range(1, len(aggregate)):
        current = float(values.iloc[index])
        impact = current - previous
        projection_date = pd.to_datetime(aggregate.loc[index, "projection_date"])
        rows.append(
            {
                "driver": projection_date.strftime("%b %Y"),
                "impact": impact,
                "start": min(previous, current),
                "end": max(previous, current),
                "kind": "increase" if impact >= 0 else "decrease",
                "sort": index,
            }
        )
        previous = current

    rows.append(
        {
            "driver": "Closing RWA",
            "impact": previous,
            "start": 0.0,
            "end": previous,
            "kind": "closing",
            "sort": len(aggregate),
        }
    )

    frame = pd.DataFrame(rows)
    frame["start_m"] = frame["start"] / 1_000_000
    frame["end_m"] = frame["end"] / 1_000_000
    y_padding = max(frame["end_m"].max() * 0.035, 1.0)
    frame["label_y"] = frame[["start_m", "end_m"]].max(axis=1) + y_padding
    frame["chart_label"] = frame.apply(
        lambda row: (
            format_signed_millions(row["impact"])
            if row["kind"] not in {"opening", "closing"}
            else format_unsigned_millions(row["impact"])
        ),
        axis=1,
    )
    return frame


def runoff_waterfall_chart(frame: pd.DataFrame) -> alt.LayerChart:
    """Render a dark themed waterfall from prepared run-off deltas."""
    if frame.empty:
        return alt.Chart(pd.DataFrame({"driver": [], "impact": []})).mark_bar()

    base = alt.Chart(frame).encode(
        x=alt.X(
            "driver:N",
            sort=alt.SortField("sort"),
            title=None,
            axis=alt.Axis(labelAngle=0, labelLimit=88),
        )
    )
    bars = base.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=40).encode(
        y=alt.Y("start_m:Q", title="PLN (Millions)"),
        y2="end_m:Q",
        color=alt.Color(
            "kind:N",
            scale=alt.Scale(
                domain=["opening", "increase", "decrease", "closing"],
                range=["#0f62fe", "#f59f00", "#17b26a", "#16a34a"],
            ),
            legend=None,
        ),
        tooltip=[
            "driver",
            alt.Tooltip("impact:Q", title="Impact PLN", format=",.0f"),
            alt.Tooltip("end:Q", title="RWA PLN", format=",.0f"),
        ],
    )
    labels = base.mark_text(dy=-6, color="#edf5ff", fontWeight="bold").encode(
        y=alt.Y("label_y:Q"),
        text="chart_label:N",
    )
    return (
        (bars + labels)
        .properties(height=372, background="transparent")
        .configure_axis(
            gridColor="rgba(126, 158, 203, 0.16)",
            labelColor="#c8d5e8",
            titleColor="#c8d5e8",
        )
        .configure_view(stroke=None)
    )


def runoff_driver_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the right-side driver table for the run-off waterfall."""
    if frame.empty:
        return pd.DataFrame(columns=["Driver", "Impact (PLN)", "% of Change"])

    deltas = frame[~frame["kind"].isin(["opening", "closing"])].copy()
    total_change = float(deltas["impact"].sum())
    deltas["Driver"] = deltas["driver"]
    deltas["Impact (PLN)"] = deltas["impact"].map(format_signed_full_money)
    if total_change == 0:
        deltas["% of Change"] = "n/a"
    else:
        deltas["% of Change"] = deltas["impact"].map(lambda value: f"{value / total_change:.1%}")

    table = deltas[["Driver", "Impact (PLN)", "% of Change"]]
    total = pd.DataFrame(
        [
            {
                "Driver": "Total Change",
                "Impact (PLN)": format_signed_full_money(total_change),
                "% of Change": "100.0%" if total_change else "n/a",
            }
        ]
    )
    return pd.concat([table, total], ignore_index=True)


def methodology_selector() -> str:
    """Render the methodology switch with a Streamlit-version-safe fallback."""
    control = getattr(st.sidebar, "segmented_control", None)
    if callable(control):
        return str(
            control(
                "Metodologia",
                options=RUNOFF_METHODOLOGY_OPTIONS,
                default=MODEL_RUNOFF,
            )
            or MODEL_RUNOFF
        )
    return str(
        st.sidebar.radio(
            "Metodologia",
            RUNOFF_METHODOLOGY_OPTIONS,
            index=RUNOFF_METHODOLOGY_OPTIONS.index(MODEL_RUNOFF),
        )
    )


def render_runoff_methodology(selected_methodology: str, as_of_date: date) -> None:
    """Run and render exactly one selected run-off methodology."""
    st.subheader(selected_methodology)
    if selected_methodology == MODEL_RUNOFF:
        projected_months = st.slider("Horyzont run-off w miesiacach", 1, 24, 24)
        assets = st.slider("Aktywa w run-off", 10, 300, 100, 10)
        with st.spinner("Liczenie run-off obecnego portfela..."):
            runoff = cached_runoff_projection(as_of_date, projected_months, assets)
        render_runoff(runoff)
        return


def render_current(snapshot) -> None:
    """Render point-in-time RWA metrics and portfolio cuts."""
    total_rwa = snapshot.summary[RWA_FINAL_FIELD]
    total_exposure = snapshot.summary["total_exposure_amount"]
    density = snapshot.summary["basel_3_1_rwa_density"]

    col_rwa, col_exposure, col_density, col_failures = st.columns(4)
    col_rwa.metric("Credit RWA", format_money(total_rwa))
    col_exposure.metric("Exposure amount", format_money(total_exposure))
    col_density.metric("RWA density", format_pct(density))
    col_failures.metric("Bledy walidacji", snapshot.summary["output_failure_records"])

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("RWA wedlug klasy ekspozycji")
        chart = (
            alt.Chart(snapshot.by_entity)
            .mark_bar()
            .encode(
                x=alt.X("entity_class:N", title="Klasa ekspozycji"),
                y=alt.Y(f"{RWA_FINAL_FIELD}:Q", title="Basel 3.1 row-level RWA"),
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

    st.subheader("Najwieksze kontrybutory RWA")
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
    col_assets.metric("Aktywa w run-off", projection.selected_asset_count)
    col_dates.metric("Punkty czasowe", len(projection.aggregate))
    col_errors.metric("Bledy run-off", len(projection.errors))

    line_frame = projection.aggregate.rename(columns=RWA_LABELS)
    measures = list(RWA_LABELS.values())
    long_frame = line_frame.melt(
        id_vars="projection_date",
        value_vars=measures,
        var_name="Miara",
        value_name="RWA",
    )
    chart = (
        alt.Chart(long_frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("projection_date:T", title="Data"),
            y=alt.Y("RWA:Q", title="RWA"),
            color=alt.Color("Miara:N"),
            tooltip=[
                alt.Tooltip("projection_date:T", title="Data"),
                "Miara",
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
            x=alt.X("projection_date:T", title="Data"),
            y=alt.Y("RWA:Q", title="Basel 3.1 row-level RWA"),
            tooltip=[
                alt.Tooltip("projection_date:T", title="Data"),
                "id",
                "entity_class",
                "sub_class",
                alt.Tooltip("RWA:Q", format=",.0f"),
            ],
        )
    )
    st.altair_chart(asset_chart, width="stretch")
    st.dataframe(format_table(asset_frame), width="stretch", hide_index=True)


def render_input_package(overview) -> None:
    """Render generated-input manifest and data-quality diagnostics."""
    col_version, col_status, col_seed, col_files = st.columns(4)
    col_version.metric("Wersja", overview.manifest["version_id"])
    col_status.metric("Walidacja", overview.manifest["validation_status"])
    col_seed.metric("Seed", overview.manifest["random_seed"])
    col_files.metric("Pliki", len(overview.manifest["generated_files"]))

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Wygenerowane pliki")
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


def format_full_money(value: float | int | None) -> str:
    """Format full PLN values for headline dashboard cards."""
    if value is None:
        return "n/a"
    return f"{float(value):,.0f}"


def format_signed_full_money(value: float | int | None) -> str:
    """Format signed PLN values for movement attribution."""
    if value is None:
        return "n/a"
    return f"{float(value):+,.0f}"


def format_unsigned_millions(value: float | int | None) -> str:
    """Format a non-signed compact millions label."""
    if value is None:
        return "n/a"
    return f"{float(value) / 1_000_000:,.0f}M"


def format_signed_millions(value: float | int | None) -> str:
    """Format a signed compact millions label."""
    if value is None:
        return "n/a"
    return f"{float(value) / 1_000_000:+,.0f}M"


def format_pp(value: float | int | None) -> str:
    """Format a ratio delta as percentage points."""
    if value is None:
        return "n/a"
    return f"{float(value) * 100:+.2f} pp"


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


if __name__ == "__main__":
    main()
