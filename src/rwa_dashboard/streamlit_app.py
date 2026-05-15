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
    RWA_FINAL_FIELD: "Basel 3.1 row-level proxy",
}
MODEL_RUNOFF = "Run-off f(x,t)"
LEGACY_METHODOLOGY_LABEL = MODEL_RUNOFF
RUNOFF_METHODOLOGY_OPTIONS = (MODEL_RUNOFF,)
CALCULATOR_MATURITY_LABEL = "Proxy calculator"
CALCULATOR_POSITIONING_NOTE = (
    "Methodology scope: proxy calculator control tower; on this branch, legacy scope is limited "
    "to Run-off f(x,t), not a full regulatory-grade RWA engine."
)
CALCULATOR_POSITIONING_DETAILS = (
    "Uses prepared pre-prod input data, generated scenario assumptions and deterministic "
    "calculator outputs for decision support.",
    "Legacy methodology on legacy_prep is Run-off f(x,t) only.",
    "Does not replace bank-approved regulatory reporting, model validation, jurisdictional "
    "rule interpretation or supervisory sign-off.",
)


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
    st.set_page_config(page_title="RWA Run-off", layout="wide")

    default_date = default_as_of_date()
    st.sidebar.title("Parametry")
    as_of_date = st.sidebar.date_input("Dzien kalkulacji", value=default_date)
    selected_methodology = methodology_selector()
    snapshot = cached_current(as_of_date)

    st.title("RWA Run-off Dashboard")
    st.caption(f"{CALCULATOR_MATURITY_LABEL}, as-of {as_of_date.isoformat()}")
    render_calculator_positioning()

    tab_current, tab_model, tab_data = st.tabs(
        ["RWA dzisiaj", "Run-off methodology", "Dane i jakosc"]
    )

    with tab_current:
        render_current(snapshot)
        render_regulatory_capital(cached_regulatory_capital(as_of_date))

    with tab_model:
        render_runoff_methodology(selected_methodology, as_of_date)

    with tab_data:
        render_input_package(cached_input_package())


def render_calculator_positioning() -> None:
    """Render the explicit methodology-scope warning requested for stakeholder alignment."""
    st.warning(CALCULATOR_POSITIONING_NOTE)
    with st.expander("Methodology scope and limitations", expanded=False):
        for detail in CALCULATOR_POSITIONING_DETAILS:
            st.markdown(f"- {detail}")


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
    st.info("Legacy methodology on this branch: Run-off f(x,t) only.")
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
    col_rwa.metric("Credit RWA row proxy", format_money(total_rwa))
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
                y=alt.Y(f"{RWA_FINAL_FIELD}:Q", title="Basel 3.1 row-level proxy RWA"),
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
            y=alt.Y("RWA:Q", title="Basel 3.1 row-level proxy RWA"),
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
