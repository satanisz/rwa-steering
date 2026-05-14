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
    monthly_projection,
    steering_simulation,
)

RWA_LABELS = {
    "basel_3_0_rwa": "Basel 3.0",
    RWA_FOUNDATION_FIELD: "Basel 3.1 foundation",
    RWA_STANDARDISED_FIELD: "Basel 3.1 standardised",
    RWA_FINAL_FIELD: "Basel 3.1 final",
}


@st.cache_data(ttl=600, show_spinner=False)
def cached_current(as_of_date: date):
    """Cache current RWA calculation across Streamlit reruns."""
    return current_rwa_snapshot(as_of_date)


@st.cache_data(ttl=600, show_spinner=False)
def cached_monthly_projection(as_of_date: date, months: int, assets: int):
    """Cache monthly projection output across Streamlit reruns."""
    return monthly_projection(as_of_date, projected_months=months, top_n_assets=assets)


@st.cache_data(ttl=600, show_spinner=False)
def cached_steering(as_of_date: date, scenarios: tuple[str, ...], assets: int, top_n: int):
    """Cache scenario steering output across Streamlit reruns."""
    return steering_simulation(
        as_of_date=as_of_date,
        scenarios=list(scenarios),
        top_n_assets=assets,
        top_n_recommendations=top_n,
    )


@st.cache_data(ttl=600, show_spinner=False)
def cached_input_package():
    """Cache generated-input metadata across Streamlit reruns."""
    return input_package_overview()


def main() -> None:
    """Render the RWA steering simulation dashboard."""
    st.set_page_config(page_title="RWA Steering", layout="wide")

    default_date = default_as_of_date()
    st.sidebar.title("Parametry")
    as_of_date = st.sidebar.date_input("Dzień kalkulacji", value=default_date)
    projected_months = st.sidebar.slider("Horyzont miesięczny", 1, 24, 24)
    projection_assets = st.sidebar.slider("Aktywa w projekcji miesięcznej", 10, 300, 100, 10)
    steering_assets = st.sidebar.slider("Aktywa w scenariuszach", 10, 200, 75, 5)
    scenarios = st.sidebar.multiselect(
        "Scenariusze",
        ["BASE", "DOWNSIDE", "STRESS", "RECOVERY"],
        default=["BASE", "STRESS"],
    )
    top_n_recommendations = st.sidebar.slider("Rekomendacje", 1, 25, 10)

    selected_scenarios = tuple(scenarios or ["BASE"])
    snapshot = cached_current(as_of_date)

    st.title("RWA Steering Dashboard")
    st.caption(f"Dane syntetyczne pre-prod, as-of {as_of_date.isoformat()}")

    tab_current, tab_projection, tab_scenarios, tab_data = st.tabs(
        ["Dzisiejsze RWA", "Projekcja miesięczna", "Scenariusze", "Dane i jakość"]
    )

    with tab_current:
        render_current(snapshot)

    with tab_projection:
        with st.spinner("Liczenie projekcji miesięcznej..."):
            projection = cached_monthly_projection(as_of_date, projected_months, projection_assets)
        render_projection(projection)

    with tab_scenarios:
        with st.spinner("Liczenie scenariuszy steeringowych..."):
            steering = cached_steering(
                as_of_date,
                selected_scenarios,
                steering_assets,
                top_n_recommendations,
            )
        render_steering(steering)

    with tab_data:
        render_input_package(cached_input_package())


def render_current(snapshot) -> None:
    """Render point-in-time RWA metrics and portfolio cuts."""
    total_rwa = snapshot.summary[RWA_FINAL_FIELD]
    total_exposure = snapshot.summary["total_exposure_amount"]
    density = snapshot.summary["basel_3_1_rwa_density"]

    col_rwa, col_exposure, col_density, col_failures = st.columns(4)
    col_rwa.metric("Basel 3.1 final RWA", format_money(total_rwa))
    col_exposure.metric("Exposure amount", format_money(total_exposure))
    col_density.metric("RWA density", format_pct(density))
    col_failures.metric("Błędy walidacji", snapshot.summary["output_failure_records"])

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("RWA według klasy ekspozycji")
        chart = (
            alt.Chart(snapshot.by_entity)
            .mark_bar()
            .encode(
                x=alt.X("entity_class:N", title="Klasa ekspozycji"),
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
        st.altair_chart(chart, use_container_width=True)
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
        st.altair_chart(stack, use_container_width=True)

    st.subheader("Największe kontrybutory RWA")
    st.dataframe(format_table(snapshot.top_assets), use_container_width=True, hide_index=True)


def render_projection(projection) -> None:
    """Render monthly calculator-based projection charts."""
    col_assets, col_dates, col_errors = st.columns(3)
    col_assets.metric("Aktywa w symulacji", projection.selected_asset_count)
    col_dates.metric("Punkty czasowe", len(projection.aggregate))
    col_errors.metric("Błędy projekcji", len(projection.errors))

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
    st.altair_chart(chart, use_container_width=True)

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
            y=alt.Y("RWA:Q", title="Basel 3.1 final RWA"),
            tooltip=[
                alt.Tooltip("projection_date:T", title="Data"),
                "id",
                "entity_class",
                "sub_class",
                alt.Tooltip("RWA:Q", format=",.0f"),
            ],
        )
    )
    st.altair_chart(asset_chart, use_container_width=True)
    st.dataframe(format_table(asset_frame), use_container_width=True, hide_index=True)


def render_steering(steering) -> None:
    """Render scenario summaries, attribution and recommended steering actions."""
    col_assets, col_dates, col_status = st.columns(3)
    col_assets.metric("Aktywa w scenariuszach", steering.selected_asset_count)
    col_dates.metric("Horyzonty", len(steering.projection_dates))
    col_status.metric("Status inputów", steering.package_status or "unknown")

    scenario_chart = (
        alt.Chart(steering.summaries)
        .mark_line(point=True)
        .encode(
            x=alt.X("projection_date:T", title="Data"),
            y=alt.Y("projected_rwa:Q", title="Projected RWA"),
            color=alt.Color("scenario_id:N", title="Scenariusz"),
            tooltip=[
                "scenario_id",
                "regime_label",
                alt.Tooltip("projection_date:T", title="Data"),
                alt.Tooltip("projected_rwa:Q", format=",.0f"),
                alt.Tooltip("rwa_delta_pct:Q", format=".2%"),
            ],
        )
    )
    st.altair_chart(scenario_chart, use_container_width=True)

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
            color=alt.Color("scenario_id:N", title="Scenariusz"),
            column=alt.Column("scenario_id:N", title=None),
            tooltip=["scenario_id", "Driver", alt.Tooltip("RWA delta:Q", format=",.0f")],
        )
    )
    st.subheader(f"Atrybucja na {pd.Timestamp(latest_date).date().isoformat()}")
    st.altair_chart(attribution_chart, use_container_width=True)

    st.subheader("Rekomendowane działania")
    st.dataframe(format_table(steering.recommendations), use_container_width=True, hide_index=True)


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
        st.dataframe(overview.row_counts, use_container_width=True, hide_index=True)
    with right:
        st.subheader("Quality flags")
        st.dataframe(overview.data_quality_summary, use_container_width=True, hide_index=True)

    st.subheader("Quality gates")
    gates = pd.DataFrame({"quality_gate": overview.validation_report["quality_gates"]})
    st.dataframe(gates, use_container_width=True, hide_index=True)


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
