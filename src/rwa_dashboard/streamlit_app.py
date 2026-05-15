from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from rwa_dashboard.data import (
    RWA_FINAL_FIELD,
    RWA_FOUNDATION_FIELD,
    RWA_STANDARDISED_FIELD,
    available_projection_dates,
    current_rwa_snapshot,
    default_as_of_date,
    forecast_projection,
    input_package_overview,
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
    RWA_FINAL_FIELD: "Basel 3.1 row-level proxy",
}
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
CALCULATOR_MATURITY_LABEL = "Proxy/legacy calculator"
CALCULATOR_POSITIONING_NOTE = (
    "Methodology scope: proxy/legacy calculator and steering control tower; "
    "not a full regulatory-grade RWA engine."
)
CALCULATOR_POSITIONING_DETAILS = (
    "Uses prepared pre-prod input data, generated scenario assumptions and deterministic "
    "calculator outputs for decision support.",
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


def main() -> None:
    """Render the RWA steering simulation dashboard."""
    st.set_page_config(page_title="RWA Steering", layout="wide")

    default_date = default_as_of_date()
    st.sidebar.title("Parametry")
    as_of_date = st.sidebar.date_input("Dzień kalkulacji", value=default_date)
    selected_model = model_selector()
    scenario_id = st.sidebar.selectbox(
        "Scenariusz",
        SCENARIO_OPTIONS,
        index=SCENARIO_OPTIONS.index("STRESS") if selected_model == MODEL_RATS else 0,
    )

    snapshot = cached_current(as_of_date)

    st.title("RWA Steering Dashboard")
    st.caption(f"{CALCULATOR_MATURITY_LABEL}, as-of {as_of_date.isoformat()}")
    render_calculator_positioning()

    tab_current, tab_model, tab_data = st.tabs(["RWA dzisiaj", "Steering model", "Dane i jakość"])

    with tab_current:
        render_current(snapshot)
        render_regulatory_capital(cached_regulatory_capital(as_of_date))

    with tab_model:
        render_selected_model(selected_model, as_of_date, str(scenario_id))

    with tab_data:
        render_input_package(cached_input_package())


def render_calculator_positioning() -> None:
    """Render the explicit methodology-scope warning requested for stakeholder alignment."""
    st.warning(CALCULATOR_POSITIONING_NOTE)
    with st.expander("Methodology scope and limitations", expanded=False):
        for detail in CALCULATOR_POSITIONING_DETAILS:
            st.markdown(f"- {detail}")


def model_selector() -> str:
    """Render the steering model switch with a Streamlit-version-safe fallback."""
    control = getattr(st.sidebar, "segmented_control", None)
    if callable(control):
        return str(
            control(
                "Model steeringu",
                options=STEERING_MODEL_OPTIONS,
                default=MODEL_FORECAST,
            )
            or MODEL_FORECAST
        )
    return str(
        st.sidebar.radio(
            "Model steeringu",
            STEERING_MODEL_OPTIONS,
            index=STEERING_MODEL_OPTIONS.index(MODEL_FORECAST),
        )
    )


def render_selected_model(selected_model: str, as_of_date: date, scenario_id: str) -> None:
    """Run and render exactly one selected steering model."""
    st.subheader(selected_model)
    if selected_model == MODEL_RUNOFF:
        projected_months = st.slider("Horyzont run-off w miesiącach", 1, 24, 24)
        assets = st.slider("Aktywa w run-off", 10, 300, 100, 10)
        with st.spinner("Liczenie run-off obecnego portfela..."):
            runoff = cached_runoff_projection(as_of_date, projected_months, assets)
        render_runoff(runoff)
        return

    if selected_model == MODEL_SCENARIO_FORECAST:
        assets = st.slider("Aktywa w scenario forecast", 3, 150, 50, 1)
        with st.spinner("Liczenie wszystkich scenariuszy forecastu..."):
            forecast = cached_forecast_projection(as_of_date, assets)
        render_forecast(forecast)
        return

    if selected_model == MODEL_FORECAST:
        model_type = st.selectbox("Silnik forecastu", FORECAST_ENGINE_OPTIONS)
        horizon_months = st.slider("Horyzont forecastu w miesiącach", 1, 36, 12)
        path_count = st.slider("Trajektorie Monte Carlo", 2, 100, 12, 1)
        assets = st.slider("Aktywa w forecast", 3, 100, 25, 1)
        with st.spinner("Symulacja VAR/LSTM i Monte Carlo trajectories..."):
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
        assets = st.slider("Aktywa w steering", 3, 150, 50, 1)
        recommendations = st.slider("Rekomendacje", 1, 25, 10, 1)
        with st.spinner("Liczenie scenario steering, attribution i rekomendacji..."):
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
        st.error("Brak wygenerowanych dat projekcji dla wybranego as-of.")
        return
    projection_date = st.selectbox(
        "Data optymalizacji",
        projection_dates,
        index=len(projection_dates) - 1,
        format_func=lambda value: value.isoformat(),
    )
    assets = st.slider("Aktywa w RATS", 4, 80, 25, 1)
    candidates = st.slider("Kandydaci UEI", 4, 50, 20, 1)
    legs = st.slider("Maksymalna liczba legs", 1, 10, 4, 1)
    particles = st.slider("Particles", 4, 40, 10, 1)
    iterations = st.slider("Iterations", 1, 40, 8, 1)
    with st.spinner("Liczenie Risk-Aware Trading Swarm..."):
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
    col_rwa.metric("Credit RWA row proxy", format_money(total_rwa))
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

    st.subheader("Największe kontrybutory RWA")
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
    col_errors.metric("Błędy run-off", len(projection.errors))

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


def render_forecast(forecast) -> None:
    """Render scenario forecast of input variables and recalculated RWA."""
    col_assets, col_scenarios, col_dates, col_errors = st.columns(4)
    col_assets.metric("Aktywa w forecast", forecast.selected_asset_count)
    col_scenarios.metric("Scenariusze", len(forecast.scenarios))
    col_dates.metric("Horyzonty forecast", len(forecast.projection_dates))
    col_errors.metric("Błędy forecast", len(forecast.errors))

    rwa_chart = (
        alt.Chart(forecast.aggregate)
        .mark_line(point=True)
        .encode(
            x=alt.X("projection_date:T", title="Data"),
            y=alt.Y("projected_rwa:Q", title="Projected RWA"),
            color=alt.Color("scenario_id:N", title="Scenariusz"),
            tooltip=[
                "scenario_id",
                "forecast_stage",
                alt.Tooltip("projection_date:T", title="Data"),
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
                x=alt.X("projection_date:T", title="Data"),
                y=alt.Y("forecast_exposure_amount:Q", title="Forecast exposure"),
                color=alt.Color("scenario_id:N", title="Scenariusz"),
                tooltip=[
                    "scenario_id",
                    alt.Tooltip("projection_date:T", title="Data"),
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
                x=alt.X("projection_date:T", title="Data"),
                y=alt.Y("rating_migration_count:Q", title="Rating migrations"),
                color=alt.Color("scenario_id:N", title="Scenariusz"),
                tooltip=[
                    "scenario_id",
                    alt.Tooltip("projection_date:T", title="Data"),
                    "rating_migration_count",
                    "matured_asset_count",
                ],
            )
        )
        st.altair_chart(migration_chart, width="stretch")

    latest_date = forecast.aggregate["projection_date"].max()
    latest = forecast.aggregate[forecast.aggregate["projection_date"] == latest_date]
    st.subheader(f"Forecast drivers na {pd.Timestamp(latest_date).date().isoformat()}")
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
    col_assets.metric("Aktywa w forecast", forecast.selected_asset_count)
    col_paths.metric("Trajektorie", int(summary["path_count"]))
    col_selected.metric("Wybrana ścieżka", int(summary["selected_path_id"]))
    col_breach.metric("P(breach)", format_pct(summary["breach_probability"]))

    col_rwa, col_profit, col_status = st.columns(3)
    col_rwa.metric("Selected terminal RWA", format_money(summary["selected_terminal_rwa"]))
    col_profit.metric("Selected profit", format_money(summary["selected_cumulative_profit"]))
    col_status.metric("Status inputów", forecast.package_status or "unknown")

    if forecast.portfolio_paths.empty:
        st.warning("Forecast nie zwrócił ścieżek portfela.")
        return

    path_chart = (
        alt.Chart(forecast.portfolio_paths)
        .mark_line(point=False, opacity=0.45)
        .encode(
            x=alt.X("projection_date:T", title="Data"),
            y=alt.Y("rwa:Q", title="RWA"),
            color=alt.Color("path_id:N", title="Ścieżka"),
            tooltip=[
                "path_id",
                alt.Tooltip("projection_date:T", title="Data"),
                alt.Tooltip("rwa:Q", format=",.0f"),
                alt.Tooltip("capital_ratio:Q", format=".2%"),
            ],
        )
    )
    selected_chart = (
        alt.Chart(forecast.selected_path)
        .mark_line(point=True, strokeWidth=4)
        .encode(
            x=alt.X("projection_date:T", title="Data"),
            y=alt.Y("rwa:Q", title="RWA"),
            tooltip=[
                alt.Tooltip("projection_date:T", title="Data"),
                alt.Tooltip("rwa:Q", format=",.0f"),
                alt.Tooltip("cumulative_profit:Q", format=",.0f"),
                alt.Tooltip("turnover_amount:Q", format=",.0f"),
            ],
        )
    )
    st.altair_chart(path_chart + selected_chart, width="stretch")

    selected_path_id = int(summary["selected_path_id"])
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
            x=alt.X("projection_date:T", title="Data"),
            y=alt.Y("Value:Q", title="Wartość"),
            color=alt.Color("Factor:N"),
            tooltip=[
                "Factor",
                alt.Tooltip("projection_date:T", title="Data"),
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
    col_assets.metric("Aktywa w RATS", rats.selected_asset_count)
    col_status.metric("Status inputów", rats.package_status or "unknown")
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
    col_assets.metric("Aktywa w optymalizacji", steering.selected_asset_count)
    col_dates.metric("Horyzonty", len(steering.projection_dates))
    col_status.metric("Status inputów", steering.package_status or "unknown")
    col_saving.metric("Estimated RWA saving", format_money(total_saving))

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
            color=alt.Color("scenario_id:N", title="Scenariusz"),
            column=alt.Column("scenario_id:N", title=None),
            tooltip=["scenario_id", "Driver", alt.Tooltip("RWA delta:Q", format=",.0f")],
        )
    )
    st.subheader(f"Atrybucja na {pd.Timestamp(latest_date).date().isoformat()}")
    st.altair_chart(attribution_chart, width="stretch")

    st.subheader("Rekomendowane działania")
    if steering.recommendations.empty:
        st.info("Brak rekomendacji dla wybranego portfela i scenariuszy.")
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
