from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any

from rwa_calculator.paths import NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH
from rwa_calculator.rwa_calculator.calculator import RwaCalculator
from rwa_steering.engine import RWA_FIELD, portfolio_rwa
from rwa_steering.errors import SteeringDomainError
from rwa_steering.input_package import SteeringInputPackage, load_steering_input_package
from rwa_steering.transformations import migrate_rating, parse_decimal

from .schemas import (
    ForecastRequest,
    ForecastResponse,
    ForecastSummary,
    MarketFactorStep,
    PathScore,
    PortfolioPathStep,
    SectorPathStep,
)

FORECAST_ENGINE_VERSION = "rwa-forecast-service-0.1.0"
METHODOLOGY = (
    "Autoregressive VAR/LSTM-proxy market-factor forecast with Monte Carlo portfolio "
    "trajectory generation and multi-period path scoring for RWA-aware ALM simulation."
)
MONEY_Q = Decimal("0.01")
RATE_Q = Decimal("0.000001")
MONTHS_PER_YEAR = Decimal("12")
FACTOR_NAMES = (
    "volatility_index",
    "credit_spread_bps",
    "yield_curve_slope_bps",
    "liquidity_index",
    "unemployment_proxy",
    "gdp_growth_proxy",
)


@dataclass(frozen=True)
class MacroState:
    """Market-factor vector used by the autoregressive forecast engine."""

    volatility_index: Decimal
    credit_spread_bps: Decimal
    yield_curve_slope_bps: Decimal
    liquidity_index: Decimal
    unemployment_proxy: Decimal
    gdp_growth_proxy: Decimal


@dataclass(frozen=True)
class Calibration:
    """Calibrated long-run mean, volatility and initial state for a forecast run."""

    long_run_mean: MacroState
    volatility: MacroState
    initial_state: MacroState


@dataclass
class PathAccumulator:
    """Mutable trajectory state accumulated while simulating one Monte Carlo path."""

    rows: list[dict[str, Any]]
    own_funds: Decimal
    cumulative_profit: Decimal = Decimal("0")
    cumulative_turnover: Decimal = Decimal("0")
    profit_peak: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    rwa_breach_penalty: Decimal = Decimal("0")


class RwaForecastService:
    """Forecast market parameters, generate Monte Carlo paths and score trajectories.

    The service is deliberately independent from the optimizer services. It produces simulated
    paths that can be handed to steering or RATS, while still calculating every RWA point through
    ``rwa_calculator``.
    """

    def __init__(
        self,
        nccr_mapping_path: str | Path = NCCR_MAPPING_PATH,
        country_info_path: str | Path = PREPROD_COUNTRY_INFO_PATH,
        input_package: SteeringInputPackage | None = None,
        generated_inputs_root: str | Path | None = None,
    ) -> None:
        """Initialize forecast service with calculator and generated input package."""
        self.calculator = RwaCalculator.from_files(nccr_mapping_path, country_info_path)
        if input_package is not None:
            self.input_package = input_package
        elif generated_inputs_root is not None:
            self.input_package = load_steering_input_package(generated_inputs_root)
        else:
            self.input_package = load_steering_input_package()

    def run(self, request: ForecastRequest) -> ForecastResponse:
        """Run autoregressive forecast, Monte Carlo simulation and path scoring."""
        self.input_package.ensure_jurisdiction(request.jurisdiction)
        calibration = self._calibrate(request)
        current_payload = self.calculator.calculate_batch(request.core_info)
        if current_payload["errors"]:
            raise SteeringDomainError.from_calculator_errors(current_payload["errors"])

        current_rwa = portfolio_rwa(current_payload["results"])
        own_funds = current_rwa * request.initial_capital_ratio
        market_paths: list[MarketFactorStep] = []
        portfolio_paths: list[PortfolioPathStep] = []
        sector_paths: list[SectorPathStep] = []
        scores: list[PathScore] = []

        for path_id in range(request.path_count):
            rng = random.Random(request.random_seed + path_id * 1009)  # noqa: S311
            accumulator = PathAccumulator(
                rows=[dict(row) for row in request.core_info],
                own_funds=own_funds,
            )
            state = calibration.initial_state
            path_portfolio_steps: list[PortfolioPathStep] = []

            for step in range(request.horizon_months + 1):
                projection_date = month_end_after(request.as_of_date, step)
                if step > 0:
                    state = self._next_state(state, calibration, request, rng, step)
                    turnover = self._project_rows_one_month(accumulator.rows, state, rng)
                else:
                    turnover = Decimal("0")

                payload = self.calculator.calculate_batch(accumulator.rows)
                if payload["errors"]:
                    raise SteeringDomainError.from_calculator_errors(payload["errors"])

                rwa = portfolio_rwa(payload["results"])
                exposure = portfolio_exposure(accumulator.rows)
                default_probability = default_probability_proxy(state)
                loss_probability = loss_probability_proxy(state)
                monthly_profit = monthly_portfolio_profit(accumulator.rows, default_probability)
                accumulator.cumulative_profit += monthly_profit
                accumulator.cumulative_turnover += turnover
                accumulator.own_funds += monthly_profit * request.retained_earnings_rate
                accumulator.profit_peak = max(
                    accumulator.profit_peak,
                    accumulator.cumulative_profit,
                )
                accumulator.max_drawdown = max(
                    accumulator.max_drawdown,
                    accumulator.profit_peak - accumulator.cumulative_profit,
                )
                capital_ratio = safe_ratio(accumulator.own_funds, rwa)
                breach = capital_ratio is not None and capital_ratio < request.capital_ratio_floor
                if breach:
                    accumulator.rwa_breach_penalty += (
                        request.capital_ratio_floor * rwa - accumulator.own_funds
                    )

                market_paths.append(
                    market_factor_step(
                        path_id=path_id,
                        step=step,
                        projection_date=projection_date,
                        model_type=request.model_type,
                        state=state,
                        default_probability=default_probability,
                        loss_probability=loss_probability,
                    )
                )
                portfolio_step = PortfolioPathStep(
                    path_id=path_id,
                    step=step,
                    projection_date=projection_date,
                    exposure_amount=exposure.quantize(MONEY_Q),
                    rwa=rwa.quantize(MONEY_Q),
                    own_funds=accumulator.own_funds.quantize(MONEY_Q),
                    capital_ratio=quantize_optional_rate(capital_ratio),
                    monthly_profit=monthly_profit.quantize(MONEY_Q),
                    cumulative_profit=accumulator.cumulative_profit.quantize(MONEY_Q),
                    turnover_amount=turnover.quantize(MONEY_Q),
                    max_drawdown=accumulator.max_drawdown.quantize(MONEY_Q),
                    rwa_breach=breach,
                )
                portfolio_paths.append(portfolio_step)
                path_portfolio_steps.append(portfolio_step)
                sector_paths.extend(
                    sector_path_steps(
                        path_id=path_id,
                        step=step,
                        projection_date=projection_date,
                        rows=accumulator.rows,
                        results=payload["results"],
                    )
                )

            scores.append(self._score_path(request, accumulator, path_portfolio_steps))

        scores = sorted(scores, key=lambda item: item.objective_value, reverse=True)
        selected_path_id = scores[0].path_id
        selected_path = [step for step in portfolio_paths if step.path_id == selected_path_id]
        top_scores = scores[: request.return_top_paths]

        return ForecastResponse(
            forecast_engine_version=FORECAST_ENGINE_VERSION,
            methodology=METHODOLOGY,
            as_of_date=request.as_of_date,
            summary=forecast_summary(request, scores, selected_path_id),
            market_paths=market_paths,
            portfolio_paths=portfolio_paths,
            sector_paths=sector_paths,
            path_scores=top_scores,
            selected_path=selected_path,
            limitations=[
                "VAR parameters are calibrated from synthetic generated macro regime inputs.",
                (
                    "LSTM_PROXY is a lightweight gated recurrent approximation, "
                    "not a trained neural net."
                ),
                (
                    "Monte Carlo paths are synthetic ALM scenarios and not "
                    "production market forecasts."
                ),
            ],
            input_package_version=self.input_package.manifest.version_id,
            input_package_validation_status=self.input_package.manifest.validation_status,
        )

    def _calibrate(self, request: ForecastRequest) -> Calibration:
        """Calibrate long-run factor means and shock scales from generated macro scenarios."""
        rows = self.input_package.macro_regime_indicators
        long_run = {
            name: Decimal(str(mean(float(getattr(row, name)) for row in rows)))
            for name in FACTOR_NAMES
        }
        vol = {
            name: max(
                Decimal("0.0001"),
                Decimal(
                    str(
                        mean(abs(float(getattr(row, name)) - float(long_run[name])) for row in rows)
                    )
                )
                * Decimal("0.35"),
            )
            for name in FACTOR_NAMES
        }
        try:
            initial_row = self.input_package.macro_for(str(request.scenario_id), request.as_of_date)
        except SteeringDomainError:
            scenario_rows = [row for row in rows if row.scenario_id == str(request.scenario_id)]
            initial_row = min(
                scenario_rows,
                key=lambda row: abs((row.projection_date - request.as_of_date).days),
            )
        return Calibration(
            long_run_mean=MacroState(**long_run),
            volatility=MacroState(**vol),
            initial_state=macro_state_from_row(initial_row),
        )

    def _next_state(
        self,
        state: MacroState,
        calibration: Calibration,
        request: ForecastRequest,
        rng: random.Random,
        step: int,
    ) -> MacroState:
        """Forecast the next market-factor vector with VAR or LSTM-proxy recursion."""
        if request.model_type == "VAR":
            return var_next_state(state, calibration, rng)
        return lstm_proxy_next_state(state, calibration, rng, step)

    def _project_rows_one_month(
        self,
        rows: list[dict[str, Any]],
        state: MacroState,
        rng: random.Random,
    ) -> Decimal:
        """Project all portfolio rows by one stochastic monthly ALM step."""
        turnover = Decimal("0")
        for row in rows:
            previous_exposure = parse_decimal(row["exposure_amount"], default=Decimal("0"))
            previous_rating = str(row["counterparty_fcy_internal_rating"])
            exposure = project_exposure(row, state, rng)
            maturity = (
                parse_decimal(
                    row["residual_maturity"],
                    default=Decimal("0"),
                )
                - Decimal("1") / MONTHS_PER_YEAR
            )

            if maturity < Decimal("0"):
                renewal_probability = renewal_probability_proxy(state, row)
                if rng.random() < float(renewal_probability):
                    maturity = renewed_maturity(row)
                    row["original_maturity"] = maturity
                    exposure *= renewal_probability
                else:
                    maturity = Decimal("0")
                    exposure = Decimal("0")

            row["exposure_amount"] = max(Decimal("0"), exposure)
            row["residual_maturity"] = max(Decimal("0"), maturity)
            row["counterparty_dlgd"] = project_dlgd(row, state)
            row["counterparty_fcy_internal_rating"] = project_rating(previous_rating, state, rng)
            row["counterparty_lcy_internal_rating"] = project_rating(
                str(row["counterparty_lcy_internal_rating"]), state, rng
            )
            turnover += abs(parse_decimal(row["exposure_amount"]) - previous_exposure)
        return turnover

    def _score_path(
        self,
        request: ForecastRequest,
        accumulator: PathAccumulator,
        path_steps: list[PortfolioPathStep],
    ) -> PathScore:
        """Score a full trajectory with profit, RWA, turnover and drawdown terms."""
        terminal = path_steps[-1]
        rwa_breach_penalty = (
            accumulator.rwa_breach_penalty * request.objective_weights.rwa_breach_penalty
        )
        turnover_penalty = (
            accumulator.cumulative_turnover * request.objective_weights.turnover_penalty
        )
        drawdown_penalty = accumulator.max_drawdown * request.objective_weights.drawdown_penalty
        terminal_rwa_penalty = terminal.rwa * request.objective_weights.terminal_rwa_penalty
        objective = (
            accumulator.cumulative_profit * request.objective_weights.profit
            - rwa_breach_penalty
            - turnover_penalty
            - drawdown_penalty
            - terminal_rwa_penalty
        )
        capital_ratios = [
            step.capital_ratio for step in path_steps if step.capital_ratio is not None
        ]
        return PathScore(
            path_id=terminal.path_id,
            objective_value=objective.quantize(MONEY_Q),
            cumulative_profit=accumulator.cumulative_profit.quantize(MONEY_Q),
            rwa_breach_penalty=rwa_breach_penalty.quantize(MONEY_Q),
            turnover_penalty=turnover_penalty.quantize(MONEY_Q),
            max_drawdown_penalty=drawdown_penalty.quantize(MONEY_Q),
            terminal_rwa_penalty=terminal_rwa_penalty.quantize(MONEY_Q),
            min_capital_ratio=(min(capital_ratios).quantize(RATE_Q) if capital_ratios else None),
            terminal_rwa=terminal.rwa,
            terminal_exposure_amount=terminal.exposure_amount,
            total_turnover_amount=accumulator.cumulative_turnover.quantize(MONEY_Q),
            breached_capital_floor=any(step.rwa_breach for step in path_steps),
        )


def macro_state_from_row(row: Any) -> MacroState:
    """Convert a generated macro regime row to the internal factor vector."""
    return MacroState(
        volatility_index=row.volatility_index,
        credit_spread_bps=row.credit_spread_bps,
        yield_curve_slope_bps=row.yield_curve_slope_bps,
        liquidity_index=row.liquidity_index,
        unemployment_proxy=row.unemployment_proxy,
        gdp_growth_proxy=row.gdp_growth_proxy,
    )


def var_next_state(
    state: MacroState,
    calibration: Calibration,
    rng: random.Random,
) -> MacroState:
    """Classic VAR-style one-step autoregression with cross-factor coupling."""
    persistence = Decimal("0.72")
    spread_to_vol = Decimal("0.015") * (
        state.credit_spread_bps - calibration.long_run_mean.credit_spread_bps
    )
    vol_to_liquidity = Decimal("-0.0015") * (
        state.volatility_index - calibration.long_run_mean.volatility_index
    )
    growth_to_unemployment = Decimal("-0.20") * (
        state.gdp_growth_proxy - calibration.long_run_mean.gdp_growth_proxy
    )
    return bounded_state(
        MacroState(
            volatility_index=ar_step(
                state.volatility_index,
                calibration.long_run_mean.volatility_index,
                calibration.volatility.volatility_index,
                persistence,
                rng,
            )
            + spread_to_vol,
            credit_spread_bps=ar_step(
                state.credit_spread_bps,
                calibration.long_run_mean.credit_spread_bps,
                calibration.volatility.credit_spread_bps,
                persistence,
                rng,
            ),
            yield_curve_slope_bps=ar_step(
                state.yield_curve_slope_bps,
                calibration.long_run_mean.yield_curve_slope_bps,
                calibration.volatility.yield_curve_slope_bps,
                Decimal("0.65"),
                rng,
            ),
            liquidity_index=ar_step(
                state.liquidity_index,
                calibration.long_run_mean.liquidity_index,
                calibration.volatility.liquidity_index,
                Decimal("0.68"),
                rng,
            )
            + vol_to_liquidity,
            unemployment_proxy=ar_step(
                state.unemployment_proxy,
                calibration.long_run_mean.unemployment_proxy,
                calibration.volatility.unemployment_proxy,
                Decimal("0.82"),
                rng,
            )
            + growth_to_unemployment,
            gdp_growth_proxy=ar_step(
                state.gdp_growth_proxy,
                calibration.long_run_mean.gdp_growth_proxy,
                calibration.volatility.gdp_growth_proxy,
                Decimal("0.62"),
                rng,
            ),
        )
    )


def lstm_proxy_next_state(
    state: MacroState,
    calibration: Calibration,
    rng: random.Random,
    step: int,
) -> MacroState:
    """Lightweight gated recurrent forecast approximating an LSTM-style smoother."""
    forget_gate = Decimal("0.82")
    input_gate = Decimal("0.18") + Decimal(str(min(0.12, step / 600)))
    stress_memory = (state.volatility_index / Decimal("100")) + (
        state.credit_spread_bps / Decimal("10000")
    )
    return bounded_state(
        MacroState(
            volatility_index=gated_step(
                state.volatility_index,
                calibration.long_run_mean.volatility_index + stress_memory * Decimal("20"),
                calibration.volatility.volatility_index,
                forget_gate,
                input_gate,
                rng,
            ),
            credit_spread_bps=gated_step(
                state.credit_spread_bps,
                calibration.long_run_mean.credit_spread_bps + stress_memory * Decimal("180"),
                calibration.volatility.credit_spread_bps,
                forget_gate,
                input_gate,
                rng,
            ),
            yield_curve_slope_bps=gated_step(
                state.yield_curve_slope_bps,
                calibration.long_run_mean.yield_curve_slope_bps,
                calibration.volatility.yield_curve_slope_bps,
                Decimal("0.76"),
                input_gate,
                rng,
            ),
            liquidity_index=gated_step(
                state.liquidity_index,
                calibration.long_run_mean.liquidity_index - stress_memory * Decimal("0.25"),
                calibration.volatility.liquidity_index,
                Decimal("0.78"),
                input_gate,
                rng,
            ),
            unemployment_proxy=gated_step(
                state.unemployment_proxy,
                calibration.long_run_mean.unemployment_proxy + stress_memory * Decimal("0.08"),
                calibration.volatility.unemployment_proxy,
                Decimal("0.88"),
                input_gate,
                rng,
            ),
            gdp_growth_proxy=gated_step(
                state.gdp_growth_proxy,
                calibration.long_run_mean.gdp_growth_proxy - stress_memory * Decimal("0.04"),
                calibration.volatility.gdp_growth_proxy,
                Decimal("0.70"),
                input_gate,
                rng,
            ),
        )
    )


def ar_step(
    value: Decimal,
    long_run: Decimal,
    volatility: Decimal,
    persistence: Decimal,
    rng: random.Random,
) -> Decimal:
    """Return one scalar autoregressive step with Gaussian innovation."""
    shock = Decimal(str(rng.gauss(0, float(volatility))))
    return long_run + persistence * (value - long_run) + shock


def gated_step(
    value: Decimal,
    target: Decimal,
    volatility: Decimal,
    forget_gate: Decimal,
    input_gate: Decimal,
    rng: random.Random,
) -> Decimal:
    """Return one scalar gated recurrent update with Gaussian innovation."""
    shock = Decimal(str(rng.gauss(0, float(volatility * Decimal("0.75")))))
    return forget_gate * value + input_gate * (target - value) + shock


def bounded_state(state: MacroState) -> MacroState:
    """Clamp market factors to economically sensible synthetic bounds."""
    return MacroState(
        volatility_index=clamp(state.volatility_index, Decimal("5"), Decimal("90")),
        credit_spread_bps=clamp(state.credit_spread_bps, Decimal("20"), Decimal("900")),
        yield_curve_slope_bps=clamp(state.yield_curve_slope_bps, Decimal("-250"), Decimal("350")),
        liquidity_index=clamp(state.liquidity_index, Decimal("0.05"), Decimal("1.00")),
        unemployment_proxy=clamp(state.unemployment_proxy, Decimal("0.02"), Decimal("0.25")),
        gdp_growth_proxy=clamp(state.gdp_growth_proxy, Decimal("-0.12"), Decimal("0.08")),
    )


def project_exposure(row: dict[str, Any], state: MacroState, rng: random.Random) -> Decimal:
    """Project one exposure amount by a monthly macro-sensitive growth step."""
    exposure = parse_decimal(row["exposure_amount"], default=Decimal("0"))
    if exposure <= Decimal("0"):
        return Decimal("0")
    annual_growth = (
        state.gdp_growth_proxy
        + (state.liquidity_index - Decimal("0.50")) * Decimal("0.04")
        - state.credit_spread_bps / Decimal("10000")
    )
    class_tilt = {
        "CORP": Decimal("1.15"),
        "RETAIL": Decimal("1.05"),
        "BANK": Decimal("0.80"),
        "FI": Decimal("0.90"),
        "SOV": Decimal("0.35"),
        "PSE": Decimal("0.45"),
        "MDB": Decimal("0.35"),
    }.get(str(row.get("entity_class")), Decimal("0.75"))
    amortization = {
        "RETAIL": Decimal("0.030"),
        "CORP": Decimal("0.022"),
        "BANK": Decimal("0.015"),
        "FI": Decimal("0.018"),
    }.get(str(row.get("entity_class")), Decimal("0.010"))
    monthly_rate = annual_growth * class_tilt / MONTHS_PER_YEAR - amortization / MONTHS_PER_YEAR
    idiosyncratic = Decimal(str(rng.gauss(0, 0.006)))
    return exposure * (Decimal("1") + monthly_rate + idiosyncratic)


def project_dlgd(row: dict[str, Any], state: MacroState) -> Decimal:
    """Project DLGD with spread, volatility and liquidity stress sensitivity."""
    current = parse_decimal(row["counterparty_dlgd"], default=Decimal("0.40"))
    multiplier = Decimal("1") + state.credit_spread_bps / Decimal("10000")
    multiplier += state.volatility_index / Decimal("1000")
    multiplier += (Decimal("1") - state.liquidity_index) * Decimal("0.08")
    return clamp(current * multiplier, Decimal("0.01"), Decimal("0.95")).quantize(RATE_Q)


def project_rating(rating: str, state: MacroState, rng: random.Random) -> str:
    """Project internal rating using macro-implied downgrade and upgrade probabilities."""
    downgrade_probability = clamp(
        Decimal("0.01")
        + state.credit_spread_bps / Decimal("10000")
        + state.volatility_index / Decimal("2000")
        + state.unemployment_proxy * Decimal("0.30"),
        Decimal("0"),
        Decimal("0.55"),
    )
    upgrade_probability = clamp(
        Decimal("0.015") + max(Decimal("0"), state.gdp_growth_proxy) * Decimal("0.80"),
        Decimal("0"),
        Decimal("0.20"),
    )
    draw = Decimal(str(rng.random()))
    if draw < downgrade_probability:
        return migrate_rating(rating, 1)
    if draw > Decimal("1") - upgrade_probability:
        return migrate_rating(rating, -1)
    return rating


def default_probability_proxy(state: MacroState) -> Decimal:
    """Return annualized default probability proxy implied by simulated market factors."""
    value = Decimal("0.003")
    value += state.credit_spread_bps / Decimal("20000")
    value += state.volatility_index / Decimal("5000")
    value += state.unemployment_proxy * Decimal("0.25")
    value -= max(Decimal("0"), state.gdp_growth_proxy) * Decimal("0.15")
    return clamp(value, Decimal("0.0005"), Decimal("0.35")).quantize(RATE_Q)


def loss_probability_proxy(state: MacroState) -> Decimal:
    """Return probability proxy for loss-making monthly path increments."""
    value = default_probability_proxy(state) * Decimal("2")
    value += (Decimal("1") - state.liquidity_index) * Decimal("0.10")
    return clamp(value, Decimal("0.001"), Decimal("0.75")).quantize(RATE_Q)


def renewal_probability_proxy(state: MacroState, row: dict[str, Any]) -> Decimal:
    """Return probability that a maturing exposure is renewed in the simulated book."""
    base = Decimal("0.80") if row.get("entity_class") in {"CORP", "RETAIL"} else Decimal("0.88")
    stress_drag = state.credit_spread_bps / Decimal("2000") + state.volatility_index / Decimal(
        "300"
    )
    liquidity_support = state.liquidity_index * Decimal("0.20")
    return clamp(base - stress_drag + liquidity_support, Decimal("0.05"), Decimal("0.98"))


def renewed_maturity(row: dict[str, Any]) -> Decimal:
    """Return bounded maturity for renewed contracts."""
    original = parse_decimal(
        row.get("original_maturity") or row.get("residual_maturity"),
        default=Decimal("1"),
    )
    return clamp(original, Decimal("1"), Decimal("5"))


def monthly_portfolio_profit(
    rows: list[dict[str, Any]],
    default_probability: Decimal,
) -> Decimal:
    """Return monthly net profit proxy from yield minus expected credit loss."""
    total = Decimal("0")
    for row in rows:
        exposure = parse_decimal(row["exposure_amount"], default=Decimal("0"))
        expected_yield = parse_decimal(row.get("expected_yield"), default=Decimal("0.035"))
        dlgd = parse_decimal(row.get("counterparty_dlgd"), default=Decimal("0.40"))
        interest_margin = exposure * expected_yield / MONTHS_PER_YEAR
        expected_loss = exposure * default_probability * dlgd / MONTHS_PER_YEAR
        total += interest_margin - expected_loss
    return total


def market_factor_step(
    path_id: int,
    step: int,
    projection_date: date,
    model_type: str,
    state: MacroState,
    default_probability: Decimal,
    loss_probability: Decimal,
) -> MarketFactorStep:
    """Build a public market factor response row."""
    return MarketFactorStep(
        path_id=path_id,
        step=step,
        projection_date=projection_date,
        model_type=model_type,
        volatility_index=state.volatility_index.quantize(RATE_Q),
        credit_spread_bps=state.credit_spread_bps.quantize(RATE_Q),
        yield_curve_slope_bps=state.yield_curve_slope_bps.quantize(RATE_Q),
        liquidity_index=state.liquidity_index.quantize(RATE_Q),
        unemployment_proxy=state.unemployment_proxy.quantize(RATE_Q),
        gdp_growth_proxy=state.gdp_growth_proxy.quantize(RATE_Q),
        default_probability_proxy=default_probability,
        loss_probability_proxy=loss_probability,
    )


def sector_path_steps(
    path_id: int,
    step: int,
    projection_date: date,
    rows: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[SectorPathStep]:
    """Aggregate one Monte Carlo step by portfolio sector using calculator output rows."""
    source_by_id = {str(row["id"]): row for row in rows}
    buckets: dict[str, dict[str, Decimal | int]] = {}
    for result in results:
        row_id = str(result["id"])
        source_row = source_by_id.get(row_id, {})
        sector = str(source_row.get("sector", "UNKNOWN"))
        bucket = buckets.setdefault(
            sector,
            {
                "asset_count": 0,
                "exposure_amount": Decimal("0"),
                "rwa": Decimal("0"),
            },
        )
        bucket["asset_count"] = int(bucket["asset_count"]) + 1
        bucket["exposure_amount"] = bucket["exposure_amount"] + parse_decimal(
            source_row.get("exposure_amount"), default=Decimal("0")
        )
        bucket["rwa"] = bucket["rwa"] + parse_decimal(result[RWA_FIELD], default=Decimal("0"))

    return [
        SectorPathStep(
            path_id=path_id,
            step=step,
            projection_date=projection_date,
            sector=sector,
            asset_count=int(values["asset_count"]),
            exposure_amount=values["exposure_amount"].quantize(MONEY_Q),
            rwa=values["rwa"].quantize(MONEY_Q),
        )
        for sector, values in sorted(buckets.items())
    ]


def forecast_summary(
    request: ForecastRequest,
    scores: list[PathScore],
    selected_path_id: int,
) -> ForecastSummary:
    """Build top-level forecast summary and terminal RWA quantiles."""
    terminal_rwas = sorted(score.terminal_rwa for score in scores)
    selected = next(score for score in scores if score.path_id == selected_path_id)
    breach_count = sum(1 for score in scores if score.breached_capital_floor)
    return ForecastSummary(
        model_type=request.model_type,
        scenario_id=str(request.scenario_id),
        horizon_months=request.horizon_months,
        path_count=request.path_count,
        selected_path_id=selected_path_id,
        selected_objective_value=selected.objective_value,
        selected_terminal_rwa=selected.terminal_rwa,
        selected_cumulative_profit=selected.cumulative_profit,
        expected_terminal_rwa=(
            sum(terminal_rwas, Decimal("0")) / Decimal(len(terminal_rwas))
        ).quantize(MONEY_Q),
        p05_terminal_rwa=quantile(terminal_rwas, Decimal("0.05")),
        p95_terminal_rwa=quantile(terminal_rwas, Decimal("0.95")),
        breach_probability=(Decimal(breach_count) / Decimal(len(scores))).quantize(RATE_Q),
    )


def portfolio_exposure(rows: list[dict[str, Any]]) -> Decimal:
    """Aggregate exposure amount across simulated portfolio rows."""
    return sum(
        (parse_decimal(row["exposure_amount"], default=Decimal("0")) for row in rows),
        Decimal("0"),
    )


def month_end_after(as_of_date: date, step: int) -> date:
    """Return t0 for step zero and future month-ends for positive steps."""
    if step == 0:
        return as_of_date
    month_index = as_of_date.month - 1 + step
    year = as_of_date.year + month_index // 12
    month = month_index % 12 + 1
    day = calendar.monthrange(year, month)[1]
    return date(year, month, day)


def quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    """Return nearest-rank quantile for a sorted non-empty Decimal vector."""
    if not values:
        return Decimal("0")
    index = int((Decimal(len(values) - 1) * probability).to_integral_value())
    return values[index].quantize(MONEY_Q)


def safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Return numerator over denominator while preserving None for zero denominator."""
    if denominator == Decimal("0"):
        return None
    return numerator / denominator


def quantize_optional_rate(value: Decimal | None) -> Decimal | None:
    """Quantize optional rate-like values."""
    return value.quantize(RATE_Q) if value is not None else None


def clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    """Clamp a Decimal into a closed interval."""
    return min(max(value, lower), upper)
