from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from rwa_calculator.paths import NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH
from rwa_calculator.rwa_calculator.calculator import RwaCalculator

from .scenarios import ScenarioAssumption, get_scenario
from .schemas import (
    AttributionRow,
    ProjectionRow,
    RecommendationRow,
    ScenarioRunSummary,
    SteeringRequest,
    SteeringResponse,
)
from .transformations import parse_decimal, project_row

RWA_FIELD = "basel_3_1_rwa_final"
METHODOLOGY = (
    "Regime-aware RWA steering PoC inspired by dynamic risk budgeting and regime "
    "adaptation from Scientific Reports 2025; deterministic and explainable for hackathon use."
)


class RwaSteeringPocService:
    def __init__(
        self,
        nccr_mapping_path: str | Path = NCCR_MAPPING_PATH,
        country_info_path: str | Path = PREPROD_COUNTRY_INFO_PATH,
    ) -> None:
        self.calculator = RwaCalculator.from_files(nccr_mapping_path, country_info_path)

    def run(self, request: SteeringRequest) -> SteeringResponse:
        current_payload = self.calculator.calculate_batch(request.core_info)
        current_by_id = results_by_id(current_payload["results"])
        current_total = portfolio_rwa(current_payload["results"])

        summaries: list[ScenarioRunSummary] = []
        projections: list[ProjectionRow] = []
        attributions: list[AttributionRow] = []
        recommendations: list[RecommendationRow] = []

        for scenario_id in request.scenarios:
            scenario = get_scenario(str(scenario_id))
            for projection_date in request.projection_dates:
                projected_rows = [
                    project_row(row, scenario, request.as_of_date, projection_date)
                    for row in request.core_info
                ]
                projected_payload = self.calculator.calculate_batch(projected_rows)
                projected_by_id = results_by_id(projected_payload["results"])
                projected_total = portfolio_rwa(projected_payload["results"])

                summaries.append(
                    self._summary(scenario, projection_date, current_total, projected_total)
                )
                projections.extend(
                    self._projection_rows(
                        request=request,
                        scenario=scenario,
                        projection_date=projection_date,
                        current_rows=request.core_info,
                        projected_rows=projected_rows,
                        current_by_id=current_by_id,
                        projected_by_id=projected_by_id,
                    )
                )
                attributions.append(
                    self._attribution(
                        request=request,
                        scenario=scenario,
                        projection_date=projection_date,
                        current_total=current_total,
                        projected_total=projected_total,
                    )
                )
                recommendations.extend(
                    self._recommendations(
                        scenario=scenario,
                        projection_date=projection_date,
                        projected_rows=projected_rows,
                        projected_by_id=projected_by_id,
                        top_n=request.top_n_recommendations,
                    )
                )

        recommendations = sorted(
            recommendations,
            key=lambda item: item.recommendation_score,
            reverse=True,
        )[: request.top_n_recommendations]

        return SteeringResponse(
            methodology=METHODOLOGY,
            jurisdiction=request.jurisdiction,
            summaries=summaries,
            projections=projections,
            attributions=attributions,
            recommendations=recommendations,
            limitations=[
                "PoC uses deterministic scenario assumptions, not a trained LSTM/GMM pipeline.",
                "Regulatory calendar impact is exposed as a placeholder delta in this first PoC.",
                "Recommendations are decision-support proposals and require risk/finance review.",
            ],
        )

    def _summary(
        self,
        scenario: ScenarioAssumption,
        projection_date: date,
        current_total: Decimal,
        projected_total: Decimal,
    ) -> ScenarioRunSummary:
        delta = projected_total - current_total
        return ScenarioRunSummary(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.scenario_name,
            regime_label=scenario.regime_label,
            regime_score=scenario.regime_score,
            risk_budget_multiplier=scenario.risk_budget_multiplier,
            projection_date=projection_date,
            current_rwa=current_total,
            projected_rwa=projected_total,
            rwa_delta=delta,
            rwa_delta_pct=safe_pct(delta, current_total),
        )

    def _projection_rows(
        self,
        request: SteeringRequest,
        scenario: ScenarioAssumption,
        projection_date: date,
        current_rows: list[dict[str, Any]],
        projected_rows: list[dict[str, Any]],
        current_by_id: dict[str, dict[str, Any]],
        projected_by_id: dict[str, dict[str, Any]],
    ) -> list[ProjectionRow]:
        rows: list[ProjectionRow] = []
        for current_row, projected_row in zip(current_rows, projected_rows, strict=True):
            row_id = str(current_row["id"])
            current_rwa = parse_decimal(current_by_id[row_id][RWA_FIELD], default=Decimal("0"))
            projected_rwa = parse_decimal(projected_by_id[row_id][RWA_FIELD], default=Decimal("0"))
            delta = projected_rwa - current_rwa
            rows.append(
                ProjectionRow(
                    scenario_id=scenario.scenario_id,
                    scenario_name=scenario.scenario_name,
                    jurisdiction=request.jurisdiction,
                    as_of_date=request.as_of_date,
                    projection_date=projection_date,
                    id=row_id,
                    counterparty_gid=str(current_row["counterparty_gid"]),
                    entity_class=str(current_row["entity_class"]),
                    sub_class=str(current_row["sub_class"]),
                    exposure_ccy=str(current_row["exposure_ccy"]),
                    current_exposure_amount=parse_decimal(current_row["exposure_amount"]),
                    projected_exposure_amount=parse_decimal(projected_row["exposure_amount"]),
                    current_rating=str(current_row["counterparty_fcy_internal_rating"]),
                    projected_rating=str(projected_row["counterparty_fcy_internal_rating"]),
                    current_dlgd=parse_decimal(current_row["counterparty_dlgd"]),
                    projected_dlgd=parse_decimal(projected_row["counterparty_dlgd"]),
                    current_rwa=current_rwa,
                    projected_rwa=projected_rwa,
                    rwa_delta=delta,
                    rwa_delta_pct=safe_pct(delta, current_rwa),
                )
            )
        return rows

    def _attribution(
        self,
        request: SteeringRequest,
        scenario: ScenarioAssumption,
        projection_date: date,
        current_total: Decimal,
        projected_total: Decimal,
    ) -> AttributionRow:
        driver_totals = {
            "volume_delta": self._driver_delta(
                request, scenario, projection_date, current_total, apply_volume=True
            ),
            "maturity_delta": self._driver_delta(
                request, scenario, projection_date, current_total, apply_maturity=True
            ),
            "rating_delta": self._driver_delta(
                request, scenario, projection_date, current_total, apply_rating=True
            ),
            "dlgd_delta": self._driver_delta(
                request, scenario, projection_date, current_total, apply_dlgd=True
            ),
            "fx_delta": self._driver_delta(
                request, scenario, projection_date, current_total, apply_fx=True
            ),
        }
        regulatory_delta = Decimal("0")
        explained = sum(driver_totals.values(), regulatory_delta)
        return AttributionRow(
            scenario_id=scenario.scenario_id,
            projection_date=projection_date,
            rwa_current=current_total,
            volume_delta=driver_totals["volume_delta"],
            maturity_delta=driver_totals["maturity_delta"],
            rating_delta=driver_totals["rating_delta"],
            dlgd_delta=driver_totals["dlgd_delta"],
            fx_delta=driver_totals["fx_delta"],
            regulatory_delta=regulatory_delta,
            interaction_or_residual_delta=projected_total - current_total - explained,
            rwa_projected=projected_total,
        )

    def _driver_delta(
        self,
        request: SteeringRequest,
        scenario: ScenarioAssumption,
        projection_date: date,
        current_total: Decimal,
        **driver_flag: bool,
    ) -> Decimal:
        projected_rows = [
            project_row(
                row,
                scenario,
                request.as_of_date,
                projection_date,
                apply_volume=driver_flag.get("apply_volume", False),
                apply_maturity=driver_flag.get("apply_maturity", False),
                apply_rating=driver_flag.get("apply_rating", False),
                apply_dlgd=driver_flag.get("apply_dlgd", False),
                apply_fx=driver_flag.get("apply_fx", False),
            )
            for row in request.core_info
        ]
        return (
            portfolio_rwa(self.calculator.calculate_batch(projected_rows)["results"])
            - current_total
        )

    def _recommendations(
        self,
        scenario: ScenarioAssumption,
        projection_date: date,
        projected_rows: list[dict[str, Any]],
        projected_by_id: dict[str, dict[str, Any]],
        top_n: int,
    ) -> list[RecommendationRow]:
        candidates: list[RecommendationRow] = []
        ranked_rows = sorted(
            projected_rows,
            key=lambda row: parse_decimal(projected_by_id[str(row["id"])][RWA_FIELD]),
            reverse=True,
        )[: top_n * 2]

        for row in ranked_rows:
            before = parse_decimal(projected_by_id[str(row["id"])][RWA_FIELD])
            if before <= Decimal("0"):
                continue
            action_row = dict(row)
            action_row["exposure_amount"] = parse_decimal(row["exposure_amount"]) * Decimal("0.80")
            after = portfolio_rwa(self.calculator.calculate_batch([action_row])["results"])
            saving = max(Decimal("0"), before - after)
            cost = parse_decimal(row["exposure_amount"]) * Decimal("0.005")
            complexity = 2 if row["bond_or_loan_flag"] == "L" else 3
            score = saving * scenario.risk_budget_multiplier - cost * Decimal("0.10") - complexity
            candidates.append(
                RecommendationRow(
                    scenario_id=scenario.scenario_id,
                    projection_date=projection_date,
                    id=str(row["id"]),
                    counterparty_gid=str(row["counterparty_gid"]),
                    entity_class=str(row["entity_class"]),
                    sub_class=str(row["sub_class"]),
                    recommended_action="REDUCE_EXPOSURE",
                    action_description="Simulate 20% exposure reduction or sell-down.",
                    rwa_before_action=before,
                    rwa_after_action=after,
                    estimated_rwa_saving=saving,
                    estimated_business_cost=cost,
                    implementation_complexity=complexity,
                    recommendation_score=score,
                    reason_code="TOP_PROJECTED_RWA_CONTRIBUTOR",
                )
            )

        return candidates


def results_by_id(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in results}


def portfolio_rwa(results: list[dict[str, Any]]) -> Decimal:
    return sum(
        (parse_decimal(row[RWA_FIELD], default=Decimal("0")) for row in results),
        Decimal("0"),
    )


def safe_pct(delta: Decimal, base: Decimal) -> Decimal | None:
    if base == Decimal("0"):
        return None
    return delta / base
