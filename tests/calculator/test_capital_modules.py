from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from rwa_calculator.paths import PREPROD_CORE_INFO_PATH
from rwa_calculator.rwa_calculator.calculator import RwaCalculator, load_core_csv
from rwa_calculator.rwa_calculator.capital import (
    calculate_cva_risk,
    calculate_leverage_ratio,
    calculate_operational_risk,
    calculate_output_floor,
)
from rwa_calculator.rwa_calculator.capital_models import (
    BusinessIndicatorYear,
    CvaNettingSet,
    CvaRiskRequest,
    LeverageRatioRequest,
    OffBalanceSheetItem,
    OperationalRiskRequest,
    OutputFloorRequest,
)
from rwa_calculator.rwa_calculator.fastapi_app import create_app
from rwa_steering.input_package import load_steering_input_package

CAPITAL_PORTFOLIO_ID = "BANKING_BOOK"


def test_output_floor_uses_aggregate_pdf_example_and_phase_in() -> None:
    response = calculate_output_floor(
        OutputFloorRequest(
            calculation_date=date(2027, 1, 1),
            pre_floor_rwa=Decimal("76"),
            standardised_rwa=Decimal("140"),
            cet1_capital=Decimal("12"),
            tier1_capital=Decimal("14"),
            total_capital=Decimal("16"),
        )
    )
    phase_in = calculate_output_floor(
        OutputFloorRequest(
            calculation_date=date(2026, 1, 1),
            pre_floor_rwa=Decimal("76"),
            standardised_rwa=Decimal("140"),
            cet1_capital=Decimal("12"),
            tier1_capital=Decimal("14"),
            total_capital=Decimal("16"),
        )
    )

    assert response.floor_calibration == Decimal("0.725000")
    assert response.floor_requirement_rwa == Decimal("101.50")
    assert response.applicable_rwa == Decimal("101.50")
    assert response.output_floor_amount == Decimal("25.50")
    assert phase_in.floor_calibration == Decimal("0.700000")
    assert phase_in.floor_requirement_rwa == Decimal("98.00")


def test_operational_risk_bic_golden_example() -> None:
    response = calculate_operational_risk(
        OperationalRiskRequest(
            calculation_date=date(2026, 5, 15),
            annual_business_indicators=[
                BusinessIndicatorYear(
                    year=2024,
                    interest_leases_dividend_component=Decimal("20000000000"),
                    services_component=Decimal("10000000000"),
                    financial_component=Decimal("5000000000"),
                ),
                BusinessIndicatorYear(
                    year=2025,
                    interest_leases_dividend_component=Decimal("20000000000"),
                    services_component=Decimal("10000000000"),
                    financial_component=Decimal("5000000000"),
                ),
                BusinessIndicatorYear(
                    year=2026,
                    interest_leases_dividend_component=Decimal("20000000000"),
                    services_component=Decimal("10000000000"),
                    financial_component=Decimal("5000000000"),
                ),
            ],
            loss_data_quality_met=False,
        )
    )

    assert response.business_indicator == Decimal("35000000000.00")
    assert response.business_indicator_component == Decimal("5370000000.00")
    assert response.internal_loss_multiplier == Decimal("1.000000")
    assert response.operational_risk_rwa == Decimal("67125000000.00")


def test_cva_materiality_and_ba_cva_paths() -> None:
    materiality = calculate_cva_risk(
        CvaRiskRequest(
            calculation_date=date(2026, 5, 15),
            materiality_option_elected=True,
            aggregate_non_centrally_cleared_derivative_notional=Decimal("50000000000"),
            ccr_capital_requirement=Decimal("1250000"),
        )
    )
    ba_cva = calculate_cva_risk(
        CvaRiskRequest(
            calculation_date=date(2026, 5, 15),
            approach="BA_REDUCED",
            aggregate_non_centrally_cleared_derivative_notional=Decimal("150000000000"),
            netting_sets=[
                CvaNettingSet(
                    counterparty_id="CP1",
                    ead=Decimal("10000000"),
                    maturity_years=Decimal("2"),
                    risk_weight=Decimal("0.05"),
                )
            ],
        )
    )

    assert materiality.approach_used == "MATERIALITY_OPTION"
    assert materiality.cva_capital_requirement == Decimal("1250000.00")
    assert materiality.cva_rwa == Decimal("15625000.00")
    assert ba_cva.approach_used == "BA_REDUCED"
    assert ba_cva.cva_rwa > Decimal("0")


def test_leverage_ratio_exposure_measure_and_buffer() -> None:
    response = calculate_leverage_ratio(
        LeverageRatioRequest(
            calculation_date=date(2026, 5, 15),
            tier1_capital=Decimal("60"),
            on_balance_sheet_exposures=Decimal("1000"),
            derivative_replacement_cost=Decimal("50"),
            derivative_potential_future_exposure=Decimal("70"),
            sft_gross_exposure=Decimal("200"),
            sft_netting_benefit=Decimal("50"),
            off_balance_sheet_items=[
                OffBalanceSheetItem(
                    item_id="OBS1",
                    notional=Decimal("100"),
                    credit_conversion_factor=Decimal("0.40"),
                )
            ],
            gsib_higher_loss_absorbency_requirement=Decimal("0.02"),
        )
    )

    assert response.exposure_measure == Decimal("1310.00")
    assert response.gsib_leverage_buffer == Decimal("0.010000")
    assert response.minimum_leverage_ratio == Decimal("0.040000")
    assert response.leverage_ratio == Decimal("0.045802")


def test_capital_fastapi_endpoints() -> None:
    client = TestClient(create_app())

    output_floor = client.post(
        "/v1/output-floor/calculate",
        json={
            "calculation_date": "2027-01-01",
            "pre_floor_rwa": "76",
            "standardised_rwa": "140",
            "cet1_capital": "12",
            "tier1_capital": "14",
            "total_capital": "16",
        },
    )
    operational = client.post(
        "/v1/operational-risk/calculate",
        json={
            "calculation_date": "2026-05-15",
            "annual_business_indicators": [
                {
                    "year": 2024,
                    "interest_leases_dividend_component": "1",
                    "services_component": "1",
                    "financial_component": "1",
                },
                {
                    "year": 2025,
                    "interest_leases_dividend_component": "1",
                    "services_component": "1",
                    "financial_component": "1",
                },
                {
                    "year": 2026,
                    "interest_leases_dividend_component": "1",
                    "services_component": "1",
                    "financial_component": "1",
                },
            ],
            "loss_data_quality_met": False,
        },
    )
    leverage = client.post(
        "/v1/leverage-ratio/calculate",
        json={
            "calculation_date": "2026-05-15",
            "tier1_capital": "60",
            "on_balance_sheet_exposures": "1000",
        },
    )

    assert output_floor.status_code == 200
    assert output_floor.json()["applicable_rwa"] == "101.50"
    assert operational.status_code == 200
    assert operational.json()["operational_risk_rwa"] == "4.50"
    assert leverage.status_code == 200
    assert leverage.json()["leverage_ratio"] == "0.060000"


def test_capital_fastapi_endpoints_accept_prepared_generated_inputs() -> None:
    """Exercise capital endpoints using prepared generated CSV inputs only."""
    as_of_date = date(2026, 5, 15)
    package = load_steering_input_package()
    client = TestClient(create_app())

    cva_portfolio = package.cva_portfolio_for(CAPITAL_PORTFOLIO_ID, as_of_date)
    cva = client.post(
        "/v1/cva/calculate",
        json={
            "calculation_date": as_of_date.isoformat(),
            "approach": cva_portfolio.approach,
            "aggregate_non_centrally_cleared_derivative_notional": str(
                cva_portfolio.aggregate_non_centrally_cleared_derivative_notional
            ),
            "ccr_capital_requirement": str(cva_portfolio.ccr_capital_requirement),
            "materiality_option_elected": cva_portfolio.materiality_option_elected,
            "supervisor_approved_sa_cva": cva_portfolio.supervisor_approved_sa_cva,
            "netting_sets": [
                {
                    "counterparty_id": row.counterparty_id,
                    "ead": str(row.ead),
                    "maturity_years": str(row.maturity_years),
                    "risk_weight": str(row.risk_weight),
                    "discount_factor": str(row.discount_factor),
                }
                for row in package.cva_netting_sets_for(CAPITAL_PORTFOLIO_ID)
            ],
            "eligible_hedges": [
                {
                    "hedge_id": row.hedge_id,
                    "effective_notional": str(row.effective_notional),
                    "risk_weight": str(row.risk_weight),
                    "eligible": row.eligible,
                }
                for row in package.cva_hedges_for(CAPITAL_PORTFOLIO_ID)
            ],
            "alpha": str(cva_portfolio.alpha),
            "rho": str(cva_portfolio.rho),
            "beta": str(cva_portfolio.beta),
            "sa_cva_multiplier": str(cva_portfolio.sa_cva_multiplier),
        },
    )

    operational_losses = package.operational_losses_for(CAPITAL_PORTFOLIO_ID)
    operational = client.post(
        "/v1/operational-risk/calculate",
        json={
            "calculation_date": as_of_date.isoformat(),
            "annual_business_indicators": [
                {
                    "year": row.year,
                    "interest_leases_dividend_component": str(
                        row.interest_leases_dividend_component
                    ),
                    "services_component": str(row.services_component),
                    "financial_component": str(row.financial_component),
                }
                for row in package.operational_business_indicators_for(CAPITAL_PORTFOLIO_ID)
            ],
            "annual_operational_losses": [
                str(row.annual_operational_loss) for row in operational_losses
            ],
            "loss_data_quality_met": all(row.loss_data_quality_met for row in operational_losses),
        },
    )

    capital_position = package.capital_position_for(CAPITAL_PORTFOLIO_ID, as_of_date)
    leverage_input = package.leverage_exposure_for(CAPITAL_PORTFOLIO_ID, as_of_date)
    leverage = client.post(
        "/v1/leverage-ratio/calculate",
        json={
            "calculation_date": as_of_date.isoformat(),
            "tier1_capital": str(capital_position.tier1_capital),
            "on_balance_sheet_exposures": str(leverage_input.on_balance_sheet_exposures),
            "derivative_replacement_cost": str(leverage_input.derivative_replacement_cost),
            "derivative_potential_future_exposure": str(
                leverage_input.derivative_potential_future_exposure
            ),
            "sft_gross_exposure": str(leverage_input.sft_gross_exposure),
            "sft_netting_benefit": str(leverage_input.sft_netting_benefit),
            "off_balance_sheet_items": [
                {
                    "item_id": row.item_id,
                    "notional": str(row.notional),
                    "credit_conversion_factor": str(row.credit_conversion_factor),
                }
                for row in package.leverage_off_balance_sheet_items_for(CAPITAL_PORTFOLIO_ID)
            ],
            "tier1_deductions_eligible_for_exposure_measure": str(
                leverage_input.tier1_deductions_eligible_for_exposure_measure
            ),
            "gsib_higher_loss_absorbency_requirement": str(
                capital_position.gsib_higher_loss_absorbency_requirement
            ),
        },
    )

    calculator_payload = RwaCalculator.from_files().calculate_batch(
        load_core_csv(PREPROD_CORE_INFO_PATH)
    )
    credit_pre_floor = sum(
        Decimal(str(row["basel_3_1_rwa_foundation"])) for row in calculator_payload["results"]
    )
    credit_standardised = sum(
        Decimal(str(row["basel_3_1_rwa_standardised"])) for row in calculator_payload["results"]
    )
    portfolio = client.post(
        "/v1/capital/portfolio",
        json={
            "calculation_date": as_of_date.isoformat(),
            "credit_rwa_pre_floor": str(credit_pre_floor),
            "credit_rwa_standardised": str(credit_standardised),
            "cva_rwa": cva.json()["cva_rwa"],
            "operational_rwa": operational.json()["operational_risk_rwa"],
            "cet1_capital": str(capital_position.cet1_capital),
            "tier1_capital": str(capital_position.tier1_capital),
            "total_capital": str(capital_position.total_capital),
        },
    )

    assert cva.status_code == 200
    assert operational.status_code == 200
    assert leverage.status_code == 200
    assert portfolio.status_code == 200
    portfolio_payload = portfolio.json()
    assert Decimal(portfolio_payload["applicable_rwa"]) >= Decimal(
        portfolio_payload["pre_floor_rwa"]
    )
