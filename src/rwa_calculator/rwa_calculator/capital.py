from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .capital_models import (
    CapitalTraceStep,
    CvaRiskRequest,
    CvaRiskResponse,
    LeverageRatioRequest,
    LeverageRatioResponse,
    OperationalRiskRequest,
    OperationalRiskResponse,
    OutputFloorRequest,
    OutputFloorResponse,
    PortfolioCapitalRequest,
    PortfolioCapitalResponse,
)

MONEY_Q = Decimal("0.01")
RATE_Q = Decimal("0.000001")
RWA_MULTIPLIER = Decimal("12.5")
MATERIALITY_NOTIONAL_THRESHOLD = Decimal("100000000000")
MINIMUM_LEVERAGE_RATIO = Decimal("0.03")


def calculate_output_floor(request: OutputFloorRequest) -> OutputFloorResponse:
    """Calculate aggregate Basel III output floor with phase-in and optional cap."""
    calibration = output_floor_calibration(request.calculation_date)
    floor_requirement = request.standardised_rwa * calibration
    floored_before_cap = max(request.pre_floor_rwa, floor_requirement)
    transitional_cap = (
        request.pre_floor_rwa * Decimal("1.25") if request.apply_transitional_cap else None
    )
    applicable_rwa = (
        min(floored_before_cap, transitional_cap)
        if transitional_cap is not None
        else floored_before_cap
    )
    floor_amount = max(Decimal("0"), applicable_rwa - request.pre_floor_rwa)
    trace = [
        CapitalTraceStep(
            step_id="output_floor_calibration",
            description="Select output-floor phase-in calibration by calculation date.",
            formula="calibration = schedule(calculation_date)",
            input_values={"calculation_date": request.calculation_date.isoformat()},
            output_values={"floor_calibration": str(calibration)},
            rule_reference={
                "source_document": "Basel III final reforms",
                "section": "Output floor implementation date and transitional measures",
                "pdf_page": 143,
            },
        ),
        CapitalTraceStep(
            step_id="aggregate_floor_application",
            description="Apply the output floor to aggregate pre-floor RWA.",
            formula="applicable_rwa = max(pre_floor_rwa, calibration * standardised_rwa)",
            input_values={
                "pre_floor_rwa": str(request.pre_floor_rwa),
                "standardised_rwa": str(request.standardised_rwa),
                "apply_transitional_cap": str(request.apply_transitional_cap),
            },
            output_values={
                "floor_requirement_rwa": str(floor_requirement),
                "applicable_rwa": str(applicable_rwa),
            },
            rule_reference={
                "source_document": "Basel III final reforms",
                "section": "Output floor",
                "pdf_page": 142,
            },
        ),
    ]
    return OutputFloorResponse(
        calculation_date=request.calculation_date,
        floor_calibration=_q_rate(calibration),
        pre_floor_rwa=_q_money(request.pre_floor_rwa),
        standardised_rwa=_q_money(request.standardised_rwa),
        floor_requirement_rwa=_q_money(floor_requirement),
        floored_rwa_before_cap=_q_money(floored_before_cap),
        transitional_cap_rwa=_q_money(transitional_cap) if transitional_cap is not None else None,
        applicable_rwa=_q_money(applicable_rwa),
        output_floor_amount=_q_money(floor_amount),
        cet1_ratio_pre_floor=_safe_rate(request.cet1_capital, request.pre_floor_rwa),
        cet1_ratio=_safe_rate(request.cet1_capital, applicable_rwa),
        tier1_ratio=_safe_rate(request.tier1_capital, applicable_rwa),
        total_capital_ratio=_safe_rate(request.total_capital, applicable_rwa),
        trace=trace,
    )


def output_floor_calibration(calculation_date: date) -> Decimal:
    """Return the BCBS output-floor phase-in factor for a calculation date."""
    schedule = (
        (date(2027, 1, 1), Decimal("0.725")),
        (date(2026, 1, 1), Decimal("0.70")),
        (date(2025, 1, 1), Decimal("0.65")),
        (date(2024, 1, 1), Decimal("0.60")),
        (date(2023, 1, 1), Decimal("0.55")),
        (date(2022, 1, 1), Decimal("0.50")),
    )
    for effective_date, calibration in schedule:
        if calculation_date >= effective_date:
            return calibration
    return Decimal("0")


def calculate_operational_risk(request: OperationalRiskRequest) -> OperationalRiskResponse:
    """Calculate operational risk under the Basel III standardised approach."""
    annual_bi = [
        row.interest_leases_dividend_component + row.services_component + row.financial_component
        for row in request.annual_business_indicators
    ]
    business_indicator = sum(annual_bi, Decimal("0")) / Decimal(len(annual_bi))
    bic = business_indicator_component(business_indicator)
    loss_component = None
    if request.annual_operational_losses:
        average_loss = sum(request.annual_operational_losses, Decimal("0")) / Decimal(
            len(request.annual_operational_losses)
        )
        loss_component = average_loss * Decimal("15")

    if bic == Decimal("0"):
        ilm = Decimal("1")
    elif request.loss_data_quality_met and loss_component is not None:
        ratio = max(loss_component / bic, Decimal("0"))
        ilm = Decimal(str(math.log(math.e - 1 + float(ratio ** Decimal("0.8")))))
        ilm = max(ilm, Decimal("0"))
    else:
        ilm = request.ilm_floor

    orc = bic * ilm
    operational_rwa = orc * RWA_MULTIPLIER
    trace = [
        CapitalTraceStep(
            step_id="business_indicator",
            description="Average three-year business indicator components.",
            formula="BI = average(ILDC + SC + FC)",
            input_values={
                "annual_business_indicators": ",".join(str(value) for value in annual_bi)
            },
            output_values={"business_indicator": str(business_indicator)},
            rule_reference={
                "source_document": "Basel III final reforms",
                "section": "Operational risk standardised approach",
                "pdf_page": 133,
            },
        ),
        CapitalTraceStep(
            step_id="operational_risk_rwa",
            description="Calculate BIC, ILM, ORC and operational risk RWA.",
            formula="ORC = BIC * ILM; Operational_RWA = 12.5 * ORC",
            input_values={"business_indicator_component": str(bic), "ilm": str(ilm)},
            output_values={"operational_risk_rwa": str(operational_rwa)},
            rule_reference={
                "source_document": "Basel III final reforms",
                "section": "Operational risk",
                "pdf_page": 134,
            },
        ),
    ]
    return OperationalRiskResponse(
        calculation_date=request.calculation_date,
        business_indicator=_q_money(business_indicator),
        business_indicator_component=_q_money(bic),
        loss_component=_q_money(loss_component) if loss_component is not None else None,
        internal_loss_multiplier=_q_rate(ilm),
        operational_risk_capital=_q_money(orc),
        operational_risk_rwa=_q_money(operational_rwa),
        trace=trace,
    )


def business_indicator_component(business_indicator: Decimal) -> Decimal:
    """Return Basel III BIC using marginal coefficients and EUR bucket thresholds."""
    bucket_1 = Decimal("1000000000")
    bucket_2 = Decimal("30000000000")
    if business_indicator <= bucket_1:
        return business_indicator * Decimal("0.12")
    if business_indicator <= bucket_2:
        return bucket_1 * Decimal("0.12") + (business_indicator - bucket_1) * Decimal("0.15")
    return (
        bucket_1 * Decimal("0.12")
        + (bucket_2 - bucket_1) * Decimal("0.15")
        + (business_indicator - bucket_2) * Decimal("0.18")
    )


def calculate_cva_risk(request: CvaRiskRequest) -> CvaRiskResponse:
    """Calculate CVA capital using materiality, BA-CVA reduced/full or SA-CVA paths."""
    approach = resolve_cva_approach(request)
    materiality_applied = approach == "MATERIALITY_OPTION"
    hedge_benefit = Decimal("0")

    if materiality_applied:
        capital = request.ccr_capital_requirement
        trace_formula = "K_CVA = CCR capital requirement under materiality option"
    elif approach == "SA_CVA":
        capital = calculate_sa_cva_capital(request)
        trace_formula = "K_SA_CVA = m_CVA * aggregated weighted sensitivities"
    else:
        reduced_capital = calculate_ba_cva_reduced_capital(request)
        if approach == "BA_FULL":
            hedge_benefit = cva_hedge_benefit(request)
        capital = max(Decimal("0"), reduced_capital - hedge_benefit)
        trace_formula = "K_BA_CVA = reduced BA-CVA capital - eligible hedge benefit"

    cva_rwa = capital * RWA_MULTIPLIER
    return CvaRiskResponse(
        calculation_date=request.calculation_date,
        approach_used=approach,
        cva_capital_requirement=_q_money(capital),
        cva_rwa=_q_money(cva_rwa),
        materiality_threshold_applied=materiality_applied,
        hedge_benefit=_q_money(hedge_benefit),
        trace=[
            CapitalTraceStep(
                step_id="cva_approach_selection",
                description=(
                    "Select CVA approach from materiality, SA-CVA approval and BA-CVA inputs."
                ),
                formula="AUTO -> materiality option, SA-CVA if approved, otherwise BA-CVA",
                input_values={
                    "approach": request.approach,
                    "notional": str(request.aggregate_non_centrally_cleared_derivative_notional),
                    "supervisor_approved_sa_cva": str(request.supervisor_approved_sa_cva),
                },
                output_values={"approach_used": approach},
                rule_reference={
                    "source_document": "Basel III final reforms",
                    "section": "CVA risk",
                    "pdf_page": 113,
                },
            ),
            CapitalTraceStep(
                step_id="cva_capital_to_rwa",
                description="Calculate CVA capital and convert capital to RWA.",
                formula=f"{trace_formula}; CVA_RWA = 12.5 * K_CVA",
                output_values={"cva_capital": str(capital), "cva_rwa": str(cva_rwa)},
                rule_reference={
                    "source_document": "Basel III final reforms",
                    "section": "BA-CVA / SA-CVA",
                    "pdf_page": 114,
                },
            ),
        ],
    )


def resolve_cva_approach(request: CvaRiskRequest) -> str:
    """Resolve the CVA approach and enforce approval/input conditions."""
    if (
        request.materiality_option_elected
        and request.aggregate_non_centrally_cleared_derivative_notional
        <= MATERIALITY_NOTIONAL_THRESHOLD
    ):
        return "MATERIALITY_OPTION"
    if request.approach == "SA_CVA":
        if not request.supervisor_approved_sa_cva:
            raise ValueError("SA-CVA requires supervisor_approved_sa_cva=True")
        if not request.sa_cva_sensitivities:
            raise ValueError("SA-CVA requires sa_cva_sensitivities")
        return "SA_CVA"
    if request.approach == "BA_FULL":
        return "BA_FULL"
    if request.approach in {"AUTO", "BA_REDUCED", "MATERIALITY_OPTION"}:
        return "BA_REDUCED"
    raise ValueError(f"Unsupported CVA approach: {request.approach}")


def calculate_ba_cva_reduced_capital(request: CvaRiskRequest) -> Decimal:
    """Return reduced BA-CVA capital from counterparty stand-alone CVA charges."""
    by_counterparty: defaultdict[str, Decimal] = defaultdict(Decimal)
    for item in request.netting_sets:
        maturity = min(max(item.maturity_years, Decimal("1")), Decimal("5"))
        by_counterparty[item.counterparty_id] += (
            item.risk_weight * maturity * item.ead * item.discount_factor / request.alpha
        )
    scvas = list(by_counterparty.values())
    if not scvas:
        return Decimal("0")
    sum_scva = sum(scvas, Decimal("0"))
    sum_scva_squared = sum((value * value for value in scvas), Decimal("0"))
    capital_squared = (request.rho * sum_scva) ** 2 + (
        Decimal("1") - request.rho**2
    ) * sum_scva_squared
    return _sqrt(capital_squared)


def cva_hedge_benefit(request: CvaRiskRequest) -> Decimal:
    """Return simplified eligible-hedge benefit for BA-CVA full mode."""
    return request.beta * sum(
        (
            hedge.effective_notional * hedge.risk_weight
            for hedge in request.eligible_hedges
            if hedge.eligible
        ),
        Decimal("0"),
    )


def calculate_sa_cva_capital(request: CvaRiskRequest) -> Decimal:
    """Return simplified SA-CVA capital from weighted sensitivities."""
    by_risk_type: defaultdict[str, list[Decimal]] = defaultdict(list)
    correlations: defaultdict[str, list[Decimal]] = defaultdict(list)
    for sensitivity in request.sa_cva_sensitivities:
        by_risk_type[sensitivity.risk_type].append(sensitivity.weighted_sensitivity)
        correlations[sensitivity.risk_type].append(sensitivity.intra_bucket_correlation)

    total = Decimal("0")
    for risk_type, values in by_risk_type.items():
        own_terms = sum((value * value for value in values), Decimal("0"))
        cross_terms = Decimal("0")
        correlation = sum(correlations[risk_type], Decimal("0")) / Decimal(
            len(correlations[risk_type])
        )
        for index, left in enumerate(values):
            for right in values[index + 1 :]:
                cross_terms += Decimal("2") * correlation * left * right
        total += request.sa_cva_multiplier * _sqrt(max(Decimal("0"), own_terms + cross_terms))
    return total


def calculate_leverage_ratio(request: LeverageRatioRequest) -> LeverageRatioResponse:
    """Calculate Basel leverage exposure measure and leverage ratio."""
    on_balance = max(
        Decimal("0"),
        request.on_balance_sheet_exposures - request.tier1_deductions_eligible_for_exposure_measure,
    )
    derivative = request.derivative_replacement_cost + request.derivative_potential_future_exposure
    sft = max(Decimal("0"), request.sft_gross_exposure - request.sft_netting_benefit)
    off_balance = sum(
        (item.notional * item.credit_conversion_factor for item in request.off_balance_sheet_items),
        Decimal("0"),
    )
    exposure_measure = on_balance + derivative + sft + off_balance
    leverage_ratio = _safe_rate(request.tier1_capital, exposure_measure)
    buffer = request.gsib_higher_loss_absorbency_requirement * Decimal("0.50")
    minimum = MINIMUM_LEVERAGE_RATIO + buffer
    shortfall = (
        request.tier1_capital - minimum * exposure_measure
        if exposure_measure != Decimal("0")
        else None
    )
    return LeverageRatioResponse(
        calculation_date=request.calculation_date,
        tier1_capital=_q_money(request.tier1_capital),
        exposure_measure=_q_money(exposure_measure),
        on_balance_sheet_component=_q_money(on_balance),
        derivative_component=_q_money(derivative),
        sft_component=_q_money(sft),
        off_balance_sheet_component=_q_money(off_balance),
        leverage_ratio=leverage_ratio,
        minimum_leverage_ratio=_q_rate(minimum),
        gsib_leverage_buffer=_q_rate(buffer),
        leverage_ratio_surplus_or_shortfall=_q_money(shortfall) if shortfall is not None else None,
        trace=[
            CapitalTraceStep(
                step_id="leverage_exposure_measure",
                description="Aggregate leverage ratio exposure measure components.",
                formula=(
                    "exposure_measure = on_balance + derivatives + SFTs + "
                    "off_balance_sheet_equivalents"
                ),
                input_values={
                    "on_balance_sheet_exposures": str(request.on_balance_sheet_exposures),
                    "derivative_replacement_cost": str(request.derivative_replacement_cost),
                    "derivative_pfe": str(request.derivative_potential_future_exposure),
                    "sft_gross_exposure": str(request.sft_gross_exposure),
                },
                output_values={"exposure_measure": str(exposure_measure)},
                rule_reference={
                    "source_document": "Basel III final reforms",
                    "section": "Leverage ratio exposure measure",
                    "pdf_page": 145,
                },
            )
        ],
    )


def calculate_portfolio_capital(request: PortfolioCapitalRequest) -> PortfolioCapitalResponse:
    """Combine risk-type RWAs and apply the aggregate output floor."""
    pre_floor = (
        request.credit_rwa_pre_floor
        + request.cva_rwa
        + request.operational_rwa
        + request.market_rwa
        + request.securitisation_rwa
    )
    standardised = (
        request.credit_rwa_standardised
        + request.cva_rwa
        + request.operational_rwa
        + request.market_rwa
        + request.securitisation_rwa
    )
    floor = calculate_output_floor(
        OutputFloorRequest(
            calculation_date=request.calculation_date,
            pre_floor_rwa=pre_floor,
            standardised_rwa=standardised,
            cet1_capital=request.cet1_capital,
            tier1_capital=request.tier1_capital,
            total_capital=request.total_capital,
            apply_transitional_cap=request.apply_output_floor_transitional_cap,
        )
    )
    return PortfolioCapitalResponse(
        calculation_date=request.calculation_date,
        credit_rwa_pre_floor=_q_money(request.credit_rwa_pre_floor),
        credit_rwa_standardised=_q_money(request.credit_rwa_standardised),
        cva_rwa=_q_money(request.cva_rwa),
        operational_rwa=_q_money(request.operational_rwa),
        market_rwa=_q_money(request.market_rwa),
        securitisation_rwa=_q_money(request.securitisation_rwa),
        pre_floor_rwa=floor.pre_floor_rwa,
        standardised_rwa=floor.standardised_rwa,
        output_floor=floor,
        applicable_rwa=floor.applicable_rwa,
        cet1_ratio=floor.cet1_ratio,
        tier1_ratio=floor.tier1_ratio,
        total_capital_ratio=floor.total_capital_ratio,
        trace=[
            CapitalTraceStep(
                step_id="portfolio_rwa_aggregation",
                description="Aggregate credit, CVA, operational, market and securitisation RWA.",
                formula="pre_floor_rwa = credit + cva + operational + market + securitisation",
                output_values={
                    "pre_floor_rwa": str(pre_floor),
                    "standardised_rwa": str(standardised),
                },
                rule_reference={
                    "source_document": "Basel III final reforms",
                    "section": "Risk-based capital requirements",
                    "pdf_page": 142,
                },
            )
        ],
    )


def _safe_rate(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == Decimal("0"):
        return None
    return _q_rate(numerator / denominator)


def _q_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE_Q, rounding=ROUND_HALF_UP)


def _q_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _sqrt(value: Decimal) -> Decimal:
    if value <= Decimal("0"):
        return Decimal("0")
    return Decimal(str(math.sqrt(float(value))))
