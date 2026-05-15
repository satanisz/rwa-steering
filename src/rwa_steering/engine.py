from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from rwa_calculator.paths import NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH
from rwa_calculator.rwa_calculator.calculator import RwaCalculator

from .errors import SteeringDomainError
from .input_package import SteeringInputPackage, load_steering_input_package
from .scenarios import ScenarioAssumption
from .schemas import (
    AttributionRow,
    ProjectionRow,
    RecommendationRow,
    ScenarioRunSummary,
    SteeringRequest,
    SteeringResponse,
)
from .transformations import parse_decimal

RWA_FIELD = "basel_3_1_rwa_final"
METHODOLOGY = (
    "Regime-aware RWA steering inspired by dynamic risk budgeting and regime adaptation; "
    "deterministic, calculator-backed and explainable for management reporting."
)


class RwaSteeringService:
    """Run regime-aware RWA steering scenarios on top of the deterministic calculator.

    This service is the orchestration layer described in the executive plan. It never bypasses
    the RWA calculator and never predicts RWA directly. Instead it:

    1. Calculates current portfolio RWA.
    2. Projects calculator input rows under scenario assumptions.
    3. Re-runs the projected rows through ``rwa_calculator``.
    4. Builds scenario summaries, attribution and recommendation outputs.

    The implementation is deliberately deterministic. It borrows the concepts of regime
    adaptation, dynamic risk budgeting and interpretable attribution, but does not claim to train
    or deploy a production ML model.
    """

    def __init__(
        self,
        nccr_mapping_path: str | Path = NCCR_MAPPING_PATH,
        country_info_path: str | Path = PREPROD_COUNTRY_INFO_PATH,
        input_package: SteeringInputPackage | None = None,
        generated_inputs_root: str | Path | None = None,
    ) -> None:
        """Initialize the service with the calculator reference files.

        Args:
            nccr_mapping_path: Path to the NCCR/CRR mapping used by the calculator.
            country_info_path: Path to country reference data used by the calculator.
            input_package: Optional preloaded generated-input package for tests or custom runs.
            generated_inputs_root: Optional root containing the generated-input package.
        """

        self.calculator = RwaCalculator.from_files(nccr_mapping_path, country_info_path)
        if input_package is not None:
            self.input_package = input_package
        elif generated_inputs_root is not None:
            self.input_package = load_steering_input_package(generated_inputs_root)
        else:
            self.input_package = load_steering_input_package()

    def run(self, request: SteeringRequest) -> SteeringResponse:
        """Execute a full steering run for all requested scenarios and dates.

        Args:
            request: Validated steering request containing current calculator input rows,
                projection dates and scenario ids.

        Returns:
            A dashboard-ready response with scenario summaries, exposure projections,
            sequential attribution and ranked recommendations.
        """

        self.input_package.ensure_jurisdiction(request.jurisdiction)

        current_payload = self.calculator.calculate_batch(request.core_info)
        if current_payload["errors"]:
            raise SteeringDomainError.from_calculator_errors(current_payload["errors"])
        current_by_id = results_by_id(current_payload["results"])
        current_total = portfolio_rwa(current_payload["results"])

        summaries: list[ScenarioRunSummary] = []
        projections: list[ProjectionRow] = []
        attributions: list[AttributionRow] = []
        recommendations: list[RecommendationRow] = []

        for scenario_id in request.scenarios:
            for projection_date in request.projection_dates:
                scenario = self.input_package.scenario_assumption(str(scenario_id), projection_date)
                projected_rows = [
                    self.input_package.project_row(
                        row, str(scenario_id), request.as_of_date, projection_date
                    )
                    for row in request.core_info
                ]
                projected_payload = self.calculator.calculate_batch(projected_rows)
                if projected_payload["errors"]:
                    raise SteeringDomainError.from_calculator_errors(
                        projected_payload["errors"],
                        scenario_id=str(scenario_id),
                        projection_date=projection_date.isoformat(),
                    )
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
                        current_rows=request.core_info,
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
                "The service uses validated prepared inputs, not production customer data.",
                "Scenario assumptions are deterministic seed inputs, not calibrated ML forecasts.",
                "Recommendations are decision-support proposals and require risk/finance review.",
            ],
            input_package_version=self.input_package.manifest.version_id,
            input_package_validation_status=self.input_package.manifest.validation_status,
        )

    def _summary(
        self,
        scenario: ScenarioAssumption,
        projection_date: date,
        current_total: Decimal,
        projected_total: Decimal,
    ) -> ScenarioRunSummary:
        """Build portfolio-level RWA delta metrics for one scenario/date."""

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
        """Build exposure-level current-versus-projected RWA rows.

        ``current_rows`` and ``projected_rows`` are zipped with ``strict=True`` because order is
        expected to be preserved by the projection loop. A mismatch means the steering layer is
        about to report deltas against the wrong asset and should fail loudly.
        """

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
                    sector=str(current_row.get("sector", "UNKNOWN")),
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
        """Compute first-order portfolio attribution by sequential revaluation.

        Each driver is isolated by applying exactly one projection transformation and re-running
        the full portfolio through the calculator. This keeps attribution explainable and aligned
        with the regulatory calculator, while the residual discloses interaction effects between
        volume, maturity, ratings, DLGD and FX.
        """

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
        """Calculate one first-order RWA driver delta.

        ``driver_flag`` contains exactly one enabled transformation in normal use. The method
        still accepts keyword flags to keep the call site explicit and to make future multi-driver
        sensitivity tests easy to add.
        """

        projected_rows = [
            self.input_package.project_row(
                row,
                scenario.scenario_id,
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
        current_rows: list[dict[str, Any]],
        top_n: int,
    ) -> list[RecommendationRow]:
        """Generate and score first-version steering recommendations.

        Candidate assets are the top projected RWA contributors. The selected action, maximum
        reduction, business cost and implementation complexity come from generated steering
        constraints and profitability inputs. This is decision support, not automated action.
        """

        candidates: list[RecommendationRow] = []
        current_by_id = {str(row["id"]): row for row in current_rows}
        ranked_rows = sorted(
            projected_rows,
            key=lambda row: parse_decimal(projected_by_id[str(row["id"])][RWA_FIELD]),
            reverse=True,
        )[: top_n * 2]

        for row in ranked_rows:
            before = parse_decimal(projected_by_id[str(row["id"])][RWA_FIELD])
            if before <= Decimal("0"):
                continue
            current_row = current_by_id[str(row["id"])]
            constraint = self.input_package.best_reduction_constraint(current_row)
            if constraint is None or constraint.max_exposure_reduction_pct <= Decimal("0"):
                continue
            reduction_pct = min(Decimal("0.50"), constraint.max_exposure_reduction_pct)
            action_row = dict(row)
            action_row["exposure_amount"] = parse_decimal(row["exposure_amount"]) * (
                Decimal("1") - reduction_pct
            )
            action_payload = self.calculator.calculate_batch([action_row])
            if action_payload["errors"]:
                raise SteeringDomainError.from_calculator_errors(
                    action_payload["errors"],
                    scenario_id=scenario.scenario_id,
                    projection_date=projection_date.isoformat(),
                )
            after = portfolio_rwa(action_payload["results"])
            saving = max(Decimal("0"), before - after)
            profitability = self.input_package.profitability_for(str(row["id"]))
            relationship_penalty = (
                Decimal(
                    profitability.relationship_value_score
                    + profitability.strategic_importance_score
                )
                / Decimal("200")
                if profitability is not None
                else Decimal("0.50")
            )
            cost = parse_decimal(row["exposure_amount"]) * constraint.business_cost_factor
            complexity = constraint.implementation_complexity
            score = (
                saving * scenario.risk_budget_multiplier
                - cost * Decimal("0.10")
                - Decimal(complexity)
                - relationship_penalty * Decimal("1000")
            )
            candidates.append(
                RecommendationRow(
                    scenario_id=scenario.scenario_id,
                    projection_date=projection_date,
                    id=str(row["id"]),
                    counterparty_gid=str(row["counterparty_gid"]),
                    entity_class=str(row["entity_class"]),
                    sub_class=str(row["sub_class"]),
                    sector=str(current_row.get("sector", row.get("sector", "UNKNOWN"))),
                    recommended_action=constraint.action_code,
                    action_description=(
                        f"Simulate {reduction_pct:.0%} exposure reduction under generated "
                        f"{constraint.action_code} constraint."
                    ),
                    rwa_before_action=before,
                    rwa_after_action=after,
                    estimated_rwa_saving=saving,
                    estimated_business_cost=cost,
                    implementation_complexity=complexity,
                    recommendation_score=score,
                    reason_code="CONSTRAINT_AWARE_TOP_PROJECTED_RWA_CONTRIBUTOR",
                )
            )

        return candidates


def results_by_id(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index calculator output rows by exposure id."""

    return {str(row["id"]): row for row in results}


def portfolio_rwa(results: list[dict[str, Any]]) -> Decimal:
    """Aggregate Basel 3.1 final RWA from calculator output rows."""

    return sum(
        (parse_decimal(row[RWA_FIELD], default=Decimal("0")) for row in results),
        Decimal("0"),
    )


def safe_pct(delta: Decimal, base: Decimal) -> Decimal | None:
    """Return ``delta / base`` while preserving ``None`` for zero denominators."""

    if base == Decimal("0"):
        return None
    return delta / base
