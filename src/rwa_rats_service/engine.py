from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from rwa_calculator.paths import NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH
from rwa_calculator.rwa_calculator.calculator import RwaCalculator
from rwa_steering.engine import RWA_FIELD, portfolio_rwa, results_by_id, safe_pct
from rwa_steering.errors import SteeringDomainError
from rwa_steering.input_package import SteeringInputPackage, load_steering_input_package
from rwa_steering.transformations import parse_decimal

from .schemas import (
    RATSUEI,
    RATSConstraints,
    RATSIteration,
    RATSRequest,
    RATSResponse,
    RATSRunSummary,
    RATSStrategyLeg,
)

RATS_ENGINE_VERSION = "RWA-RATS-2026.2.0"
METHODOLOGY = (
    "Risk-Aware Trading Swarm for RWA steering, adapted from RATPO/RATS. "
    "The service forecasts calculator inputs, builds Unique Eligible Instruments from "
    "allowed steering actions, and runs deterministic particle-swarm search under risk, "
    "cost and concentration constraints."
)
ACTION_CODES = ("REDUCE_EXPOSURE", "SELL_DOWN", "NON_RENEWAL")
MIN_EFFECTIVE_REDUCTION = Decimal("0.005")
MONEY_Q = Decimal("0.01")
RATE_Q = Decimal("0.000001")


@dataclass(frozen=True)
class Candidate:
    """Internal Unique Eligible Instrument used by the swarm search."""

    index: int
    uei_id: str
    asset_id: str
    counterparty_gid: str
    entity_class: str
    sub_class: str
    action_code: str
    max_reduction_pct: Decimal
    business_cost_factor: Decimal
    projected_exposure_amount: Decimal
    projected_rwa: Decimal


@dataclass(frozen=True)
class StrategyLeg:
    """Internal strategy leg decoded from a particle position."""

    candidate: Candidate
    reduction_pct: Decimal
    notional_reduction_amount: Decimal
    business_cost: Decimal


@dataclass(frozen=True)
class Evaluation:
    """Objective function evaluation for one decoded strategy."""

    objective_value: Decimal
    optimized_rwa: Decimal
    rwa_saving: Decimal
    total_business_cost: Decimal
    total_reduction_amount: Decimal
    feasible: bool
    constraint_violations: list[str]
    strategy: tuple[StrategyLeg, ...]


@dataclass
class Particle:
    """Particle state for the specialized PSO recursion."""

    position: list[float]
    velocity: list[float]
    best_position: list[float]
    best_evaluation: Evaluation


class RwaRATSService:
    """Risk-aware trading swarm optimizer over forecasted RWA portfolios.

    RATS is implemented here as a deterministic, bounded Particle Swarm Optimization loop. The
    algorithm searches over strategy legs consisting of UEI index plus reduction notional. Every
    candidate strategy is applied to forecasted calculator inputs and then revalued through
    ``rwa_calculator`` so the optimized RWA remains tied to the same calculator path.
    """

    def __init__(
        self,
        nccr_mapping_path: str | Path = NCCR_MAPPING_PATH,
        country_info_path: str | Path = PREPROD_COUNTRY_INFO_PATH,
        input_package: SteeringInputPackage | None = None,
        generated_inputs_root: str | Path | None = None,
    ) -> None:
        """Initialize RATS with calculator references and generated steering inputs."""
        self.calculator = RwaCalculator.from_files(nccr_mapping_path, country_info_path)
        if input_package is not None:
            self.input_package = input_package
        elif generated_inputs_root is not None:
            self.input_package = load_steering_input_package(generated_inputs_root)
        else:
            self.input_package = load_steering_input_package()

    def optimize(self, request: RATSRequest) -> RATSResponse:
        """Run forecast, candidate generation and RATS optimization for one scenario/date."""
        self.input_package.ensure_jurisdiction(request.jurisdiction)
        scenario = self.input_package.scenario_assumption(
            str(request.scenario_id), request.projection_date
        )

        current_payload = self.calculator.calculate_batch(request.core_info)
        if current_payload["errors"]:
            raise SteeringDomainError.from_calculator_errors(current_payload["errors"])
        current_rwa = portfolio_rwa(current_payload["results"])

        projected_rows = [
            self.input_package.project_row(
                row,
                str(request.scenario_id),
                request.as_of_date,
                request.projection_date,
            )
            for row in request.core_info
        ]
        projected_payload = self.calculator.calculate_batch(projected_rows)
        if projected_payload["errors"]:
            raise SteeringDomainError.from_calculator_errors(
                projected_payload["errors"],
                scenario_id=str(request.scenario_id),
                projection_date=request.projection_date.isoformat(),
            )
        projected_results = projected_payload["results"]
        projected_by_id = results_by_id(projected_results)
        projected_rwa = portfolio_rwa(projected_results)

        candidates = self._build_candidates(
            request=request,
            projected_rows=projected_rows,
            projected_by_id=projected_by_id,
        )
        evaluation, convergence = self._run_swarm(
            request=request,
            projected_rows=projected_rows,
            candidates=candidates,
            projected_rwa=projected_rwa,
        )

        return RATSResponse(
            methodology=METHODOLOGY,
            rats_engine_version=RATS_ENGINE_VERSION,
            scenario_id=scenario.scenario_id,
            as_of_date=request.as_of_date,
            projection_date=request.projection_date,
            summary=RATSRunSummary(
                current_rwa=current_rwa,
                projected_rwa_before_strategy=projected_rwa,
                optimized_projected_rwa=evaluation.optimized_rwa,
                rwa_saving=evaluation.rwa_saving,
                rwa_saving_pct=safe_pct(evaluation.rwa_saving, projected_rwa),
                objective_value=evaluation.objective_value,
                total_business_cost=evaluation.total_business_cost,
                total_reduction_amount=evaluation.total_reduction_amount,
                selected_legs=len(evaluation.strategy),
                feasible=evaluation.feasible,
                constraint_violations=evaluation.constraint_violations,
            ),
            candidates=[candidate_to_schema(candidate) for candidate in candidates],
            best_strategy=[strategy_leg_to_schema(leg) for leg in evaluation.strategy],
            convergence=convergence,
            limitations=[
                "RATS uses prepared generated inputs and deterministic swarm search.",
                "UEIs are simplified exposure-reduction actions, not executable market orders.",
                ("Objective combines RWA saving and business cost; it is not model-risk approved."),
            ],
            input_package_version=self.input_package.manifest.version_id,
            input_package_validation_status=self.input_package.manifest.validation_status,
        )

    def _build_candidates(
        self,
        request: RATSRequest,
        projected_rows: list[dict[str, Any]],
        projected_by_id: dict[str, dict[str, Any]],
    ) -> list[Candidate]:
        """Build ranked Unique Eligible Instruments from projected rows and action constraints."""
        candidates: list[Candidate] = []
        projected_rows_by_id = {str(row["id"]): row for row in projected_rows}

        for source_row in request.core_info:
            row_id = str(source_row["id"])
            projected_row = projected_rows_by_id[row_id]
            projected_exposure = parse_decimal(projected_row["exposure_amount"])
            projected_rwa = parse_decimal(projected_by_id[row_id][RWA_FIELD])
            if projected_exposure <= Decimal("0") or projected_rwa <= Decimal("0"):
                continue

            for action_code in ACTION_CODES:
                constraint = self.input_package.constraint_for(source_row, action_code)
                if (
                    constraint is None
                    or not constraint.is_allowed
                    or constraint.max_exposure_reduction_pct <= Decimal("0")
                ):
                    continue
                max_reduction = min(
                    constraint.max_exposure_reduction_pct,
                    request.constraints.max_single_reduction_pct,
                )
                if max_reduction < MIN_EFFECTIVE_REDUCTION:
                    continue
                candidates.append(
                    Candidate(
                        index=len(candidates),
                        uei_id=f"{row_id}:{action_code}",
                        asset_id=row_id,
                        counterparty_gid=str(source_row["counterparty_gid"]),
                        entity_class=str(source_row["entity_class"]),
                        sub_class=str(source_row["sub_class"]),
                        action_code=action_code,
                        max_reduction_pct=max_reduction,
                        business_cost_factor=constraint.business_cost_factor,
                        projected_exposure_amount=projected_exposure,
                        projected_rwa=projected_rwa,
                    )
                )

        return sorted(
            candidates,
            key=lambda item: item.projected_rwa * item.max_reduction_pct,
            reverse=True,
        )[: request.top_n_candidates]

    def _run_swarm(
        self,
        request: RATSRequest,
        projected_rows: list[dict[str, Any]],
        candidates: list[Candidate],
        projected_rwa: Decimal,
    ) -> tuple[Evaluation, list[RATSIteration]]:
        """Execute the RATS particle-swarm recursion and return the best evaluation found."""
        if not candidates:
            return (
                Evaluation(
                    objective_value=Decimal("0"),
                    optimized_rwa=projected_rwa,
                    rwa_saving=Decimal("0"),
                    total_business_cost=Decimal("0"),
                    total_reduction_amount=Decimal("0"),
                    feasible=True,
                    constraint_violations=["NO_ELIGIBLE_INSTRUMENTS"],
                    strategy=(),
                ),
                [],
            )

        rng = random.Random(request.swarm.random_seed)  # noqa: S311 - deterministic optimizer seed.
        dimensions = request.constraints.max_strategy_legs * 2
        particles: list[Particle] = []
        global_best: Evaluation | None = None
        global_best_position: list[float] | None = None

        for _ in range(request.swarm.particles):
            position = self._sample_position(rng, request.constraints, candidates)
            velocity = self._sample_velocity(rng, dimensions, len(candidates))
            evaluation = self._evaluate_position(
                request=request,
                projected_rows=projected_rows,
                candidates=candidates,
                projected_rwa=projected_rwa,
                position=position,
            )
            particle = Particle(
                position=position,
                velocity=velocity,
                best_position=list(position),
                best_evaluation=evaluation,
            )
            particles.append(particle)
            if global_best is None or evaluation.objective_value > global_best.objective_value:
                global_best = evaluation
                global_best_position = list(position)

        assert global_best is not None
        assert global_best_position is not None
        convergence: list[RATSIteration] = []
        stall_iterations = 0

        for iteration in range(1, request.swarm.iterations + 1):
            inertia = inertia_weight(
                request.swarm.inertia_max, request.swarm.inertia_min, iteration
            )
            feasible_count = 0
            previous_best_objective = global_best.objective_value

            for particle in particles:
                self._move_particle(
                    particle=particle,
                    global_best_position=global_best_position,
                    inertia=inertia,
                    request=request,
                    candidate_count=len(candidates),
                    rng=rng,
                )
                evaluation = self._evaluate_position(
                    request=request,
                    projected_rows=projected_rows,
                    candidates=candidates,
                    projected_rwa=projected_rwa,
                    position=particle.position,
                )
                if evaluation.feasible:
                    feasible_count += 1
                if evaluation.objective_value > particle.best_evaluation.objective_value:
                    particle.best_evaluation = evaluation
                    particle.best_position = list(particle.position)
                if evaluation.objective_value > global_best.objective_value:
                    global_best = evaluation
                    global_best_position = list(particle.position)

            feasible_ratio = Decimal(feasible_count) / Decimal(len(particles))
            convergence.append(
                RATSIteration(
                    iteration=iteration,
                    global_best_objective=global_best.objective_value,
                    global_best_rwa_saving=global_best.rwa_saving,
                    feasible_particle_ratio=feasible_ratio.quantize(RATE_Q),
                )
            )

            if global_best.objective_value <= previous_best_objective:
                stall_iterations += 1
            else:
                stall_iterations = 0
            concentration = personal_best_concentration(particles, global_best.objective_value)
            if (
                stall_iterations >= request.swarm.max_stall_iterations
                or concentration >= request.swarm.concentration_threshold
            ):
                break

        return global_best, convergence

    def _sample_position(
        self,
        rng: random.Random,
        constraints: RATSConstraints,
        candidates: list[Candidate],
    ) -> list[float]:
        """Sample an initial 2m-dimensional RATS position."""
        index_entries = [
            rng.uniform(0, len(candidates) - 1) for _ in range(constraints.max_strategy_legs)
        ]
        notional_entries = [rng.random() for _ in range(constraints.max_strategy_legs)]
        return [*index_entries, *notional_entries]

    def _sample_velocity(
        self,
        rng: random.Random,
        dimensions: int,
        candidate_count: int,
    ) -> list[float]:
        """Sample initial particle velocity with index-aware bounds."""
        index_velocity = max(1.0, candidate_count / 3)
        half = dimensions // 2
        return [
            *[rng.uniform(-index_velocity, index_velocity) for _ in range(half)],
            *[rng.uniform(-0.25, 0.25) for _ in range(half)],
        ]

    def _move_particle(
        self,
        particle: Particle,
        global_best_position: list[float],
        inertia: Decimal,
        request: RATSRequest,
        candidate_count: int,
        rng: random.Random,
    ) -> None:
        """Update particle velocity and position using the PSO recursion."""
        half = len(particle.position) // 2
        max_index_velocity = max(1.0, candidate_count / 3)
        for index, value in enumerate(particle.position):
            r_personal = rng.random()
            r_global = rng.random()
            velocity = (
                float(inertia) * particle.velocity[index]
                + float(request.swarm.cognitive_weight)
                * r_personal
                * (particle.best_position[index] - value)
                + float(request.swarm.social_weight)
                * r_global
                * (global_best_position[index] - value)
            )
            if index < half:
                velocity = min(max(velocity, -max_index_velocity), max_index_velocity)
                particle.position[index] = min(max(value + velocity, 0.0), candidate_count - 1)
            else:
                velocity = min(max(velocity, -0.50), 0.50)
                particle.position[index] = min(max(value + velocity, 0.0), 1.0)
            particle.velocity[index] = velocity

    def _evaluate_position(
        self,
        request: RATSRequest,
        projected_rows: list[dict[str, Any]],
        candidates: list[Candidate],
        projected_rwa: Decimal,
        position: list[float],
    ) -> Evaluation:
        """Decode a particle position, revalue the strategy and score the objective."""
        strategy = decode_strategy(position, candidates, request.constraints.max_strategy_legs)
        adjusted_rows = apply_strategy(projected_rows, strategy)
        payload = self.calculator.calculate_batch(adjusted_rows)
        if payload["errors"]:
            optimized_rwa = projected_rwa
            violations = ["CALCULATOR_REVALUATION_FAILED"]
            feasible = False
        else:
            optimized_rwa = portfolio_rwa(payload["results"])
            violations = []
            feasible = True

        total_cost = sum((leg.business_cost for leg in strategy), Decimal("0")).quantize(MONEY_Q)
        total_reduction = sum(
            (leg.notional_reduction_amount for leg in strategy), Decimal("0")
        ).quantize(MONEY_Q)
        projected_exposure = sum(
            (parse_decimal(row["exposure_amount"], default=Decimal("0")) for row in projected_rows),
            Decimal("0"),
        )
        rwa_saving = max(Decimal("0"), projected_rwa - optimized_rwa).quantize(MONEY_Q)
        total_reduction_limit = projected_exposure * request.constraints.max_total_reduction_pct

        if total_reduction > total_reduction_limit:
            feasible = False
            violations.append("MAX_TOTAL_REDUCTION_PCT_EXCEEDED")
        if request.constraints.max_business_cost is not None and total_cost > (
            request.constraints.max_business_cost
        ):
            feasible = False
            violations.append("MAX_BUSINESS_COST_EXCEEDED")
        if rwa_saving < request.constraints.min_rwa_saving:
            feasible = False
            violations.append("MIN_RWA_SAVING_NOT_REACHED")

        concentration_penalty = concentration_penalty_amount(strategy, request.objective_weights)
        objective = (
            rwa_saving * request.objective_weights.rwa_saving
            - total_cost * request.objective_weights.business_cost
            - concentration_penalty
        )
        if violations:
            objective -= request.objective_weights.infeasibility_penalty * Decimal(len(violations))

        return Evaluation(
            objective_value=objective.quantize(MONEY_Q),
            optimized_rwa=optimized_rwa.quantize(MONEY_Q),
            rwa_saving=rwa_saving,
            total_business_cost=total_cost,
            total_reduction_amount=total_reduction,
            feasible=feasible,
            constraint_violations=violations,
            strategy=tuple(strategy),
        )


def decode_strategy(
    position: list[float],
    candidates: list[Candidate],
    max_strategy_legs: int,
) -> list[StrategyLeg]:
    """Decode a RATS 2m-dimensional particle position into distinct UEI legs."""
    chosen: dict[int, Decimal] = {}
    for leg_index in range(max_strategy_legs):
        candidate_index = round(position[leg_index])
        candidate_index = min(max(candidate_index, 0), len(candidates) - 1)
        candidate = candidates[candidate_index]
        notional_scalar = Decimal(str(position[max_strategy_legs + leg_index]))
        reduction_pct = (notional_scalar * candidate.max_reduction_pct).quantize(RATE_Q)
        if reduction_pct < MIN_EFFECTIVE_REDUCTION:
            continue
        chosen[candidate_index] = max(chosen.get(candidate_index, Decimal("0")), reduction_pct)

    strategy: list[StrategyLeg] = []
    for candidate_index, reduction_pct in chosen.items():
        candidate = candidates[candidate_index]
        notional_reduction = (candidate.projected_exposure_amount * reduction_pct).quantize(MONEY_Q)
        strategy.append(
            StrategyLeg(
                candidate=candidate,
                reduction_pct=reduction_pct,
                notional_reduction_amount=notional_reduction,
                business_cost=(notional_reduction * candidate.business_cost_factor).quantize(
                    MONEY_Q
                ),
            )
        )
    return sorted(strategy, key=lambda item: item.notional_reduction_amount, reverse=True)


def apply_strategy(
    projected_rows: list[dict[str, Any]],
    strategy: list[StrategyLeg],
) -> list[dict[str, Any]]:
    """Apply strategy reductions to projected calculator input rows."""
    reduction_by_asset: dict[str, Decimal] = {}
    for leg in strategy:
        reduction_by_asset[leg.candidate.asset_id] = min(
            Decimal("0.95"),
            reduction_by_asset.get(leg.candidate.asset_id, Decimal("0")) + leg.reduction_pct,
        )

    adjusted_rows: list[dict[str, Any]] = []
    for row in projected_rows:
        adjusted = dict(row)
        reduction_pct = reduction_by_asset.get(str(row["id"]), Decimal("0"))
        if reduction_pct > Decimal("0"):
            exposure = parse_decimal(adjusted["exposure_amount"], default=Decimal("0"))
            adjusted["exposure_amount"] = max(
                Decimal("0"), exposure * (Decimal("1") - reduction_pct)
            )
        adjusted_rows.append(adjusted)
    return adjusted_rows


def candidate_to_schema(candidate: Candidate) -> RATSUEI:
    """Convert an internal candidate to the public UEI response model."""
    return RATSUEI(
        uei_id=candidate.uei_id,
        asset_id=candidate.asset_id,
        counterparty_gid=candidate.counterparty_gid,
        entity_class=candidate.entity_class,
        sub_class=candidate.sub_class,
        action_code=candidate.action_code,
        max_reduction_pct=candidate.max_reduction_pct,
        business_cost_factor=candidate.business_cost_factor,
        projected_exposure_amount=candidate.projected_exposure_amount.quantize(MONEY_Q),
        projected_rwa=candidate.projected_rwa.quantize(MONEY_Q),
    )


def strategy_leg_to_schema(leg: StrategyLeg) -> RATSStrategyLeg:
    """Convert an internal strategy leg to the public response model."""
    return RATSStrategyLeg(
        uei_id=leg.candidate.uei_id,
        asset_id=leg.candidate.asset_id,
        counterparty_gid=leg.candidate.counterparty_gid,
        entity_class=leg.candidate.entity_class,
        sub_class=leg.candidate.sub_class,
        action_code=leg.candidate.action_code,
        reduction_pct=leg.reduction_pct,
        notional_reduction_amount=leg.notional_reduction_amount,
        rwa_before_strategy=leg.candidate.projected_rwa.quantize(MONEY_Q),
        business_cost=leg.business_cost,
    )


def inertia_weight(max_weight: Decimal, min_weight: Decimal, iteration: int) -> Decimal:
    """Return linearly decayed inertia weight for the current RATS iteration."""
    if iteration <= 1:
        return max_weight
    decay = Decimal(iteration - 1) / Decimal(max(iteration, 1))
    return max(min_weight, max_weight - (max_weight - min_weight) * decay)


def personal_best_concentration(particles: list[Particle], best_objective: Decimal) -> Decimal:
    """Return the fraction of particles whose personal best equals the global best objective."""
    matching = sum(
        1 for particle in particles if particle.best_evaluation.objective_value == best_objective
    )
    return Decimal(matching) / Decimal(len(particles))


def concentration_penalty_amount(
    strategy: list[StrategyLeg],
    objective_weights: Any,
) -> Decimal:
    """Penalize strategies whose total reduction is concentrated in one leg."""
    total_reduction = sum((leg.notional_reduction_amount for leg in strategy), Decimal("0"))
    if total_reduction <= Decimal("0"):
        return Decimal("0")
    largest_reduction = max(
        (leg.notional_reduction_amount for leg in strategy), default=Decimal("0")
    )
    concentration_ratio = largest_reduction / total_reduction
    return (
        total_reduction * concentration_ratio * objective_weights.concentration_penalty
    ).quantize(MONEY_Q)
