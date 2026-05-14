from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from rwa_calculator.rwa_pydantic_schemas import NCCR_RATING_GRADES
from rwa_projection_service.engine import elapsed_years

from .errors import SteeringDomainError
from .missing_inputs import (
    DEFAULT_OUTPUT_ROOT,
    GENERATED_FILE_ORDER,
    DataQualityFlag,
    DlgdScenarioAssumption,
    ForecastCalendarRow,
    FxScenarioRate,
    GeneratedInputManifest,
    MacroRegimeIndicator,
    PortfolioStrategyLimit,
    ProfitabilityInput,
    RatingMigrationRow,
    RegulatoryOverlaySelection,
    ScenarioDefinition,
    SegmentGrowthAssumption,
    SteeringActionConstraint,
)
from .scenarios import ScenarioAssumption
from .transformations import parse_decimal

RISK_BUDGET_MULTIPLIERS = {
    "BASE": Decimal("1.00"),
    "DOWNSIDE": Decimal("1.15"),
    "STRESS": Decimal("1.40"),
    "RECOVERY": Decimal("0.85"),
}
MIGRATION_QUANTILES = {
    "BASE": Decimal("0.50"),
    "DOWNSIDE": Decimal("0.85"),
    "STRESS": Decimal("0.85"),
    "RECOVERY": Decimal("0.10"),
}


@dataclass(frozen=True)
class SteeringInputPackage:
    """Validated runtime view of generated steering input files.

    The generated CSV package is intentionally split into many auditable files. This loader
    turns those files into typed rows and indexed lookups so the steering engine can consume
    scenario assumptions without knowing about CSV parsing, hashing or cross-file validation.
    """

    root: Path
    manifest: GeneratedInputManifest
    scenario_definitions: list[ScenarioDefinition]
    forecast_calendar: list[ForecastCalendarRow]
    segment_growth_assumptions: list[SegmentGrowthAssumption]
    rating_migration_matrix: list[RatingMigrationRow]
    dlgd_scenario_assumptions: list[DlgdScenarioAssumption]
    fx_scenario_rates: list[FxScenarioRate]
    macro_regime_indicators: list[MacroRegimeIndicator]
    regulatory_overlay_selection: list[RegulatoryOverlaySelection]
    profitability_inputs: list[ProfitabilityInput]
    steering_action_constraints: list[SteeringActionConstraint]
    portfolio_strategy_limits: list[PortfolioStrategyLimit]
    data_quality_flags: list[DataQualityFlag]
    _scenarios: dict[str, ScenarioDefinition] = field(init=False, repr=False)
    _macro: dict[tuple[str, date], MacroRegimeIndicator] = field(init=False, repr=False)
    _growth: dict[tuple[str, int, str, str, str], SegmentGrowthAssumption] = field(
        init=False, repr=False
    )
    _dlgd: dict[tuple[str, int, str, str], DlgdScenarioAssumption] = field(init=False, repr=False)
    _fx: dict[tuple[str, date, str, str], FxScenarioRate] = field(init=False, repr=False)
    _migration: dict[tuple[str, int, str, str], list[RatingMigrationRow]] = field(
        init=False, repr=False
    )
    _profitability: dict[str, ProfitabilityInput] = field(init=False, repr=False)
    _constraints: dict[tuple[str, str, str, str], SteeringActionConstraint] = field(
        init=False, repr=False
    )
    _overlays: dict[str, RegulatoryOverlaySelection] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Build immutable-ish lookup indexes after dataclass construction."""
        object.__setattr__(
            self, "_scenarios", {row.scenario_id: row for row in self.scenario_definitions}
        )
        object.__setattr__(
            self,
            "_macro",
            {(row.scenario_id, row.projection_date): row for row in self.macro_regime_indicators},
        )
        object.__setattr__(
            self,
            "_growth",
            {
                (
                    row.scenario_id,
                    row.projection_year,
                    row.entity_class,
                    row.sub_class,
                    row.exposure_ccy,
                ): row
                for row in self.segment_growth_assumptions
            },
        )
        object.__setattr__(
            self,
            "_dlgd",
            {
                (row.scenario_id, row.projection_year, row.entity_class, row.sub_class): row
                for row in self.dlgd_scenario_assumptions
            },
        )
        object.__setattr__(
            self,
            "_fx",
            {
                (row.scenario_id, row.projection_date, row.from_ccy, row.to_ccy): row
                for row in self.fx_scenario_rates
            },
        )
        object.__setattr__(
            self,
            "_migration",
            {
                (row.scenario_id, row.projection_year, row.entity_class, row.from_rating): []
                for row in self.rating_migration_matrix
            },
        )
        for row in self.rating_migration_matrix:
            self._migration[
                (row.scenario_id, row.projection_year, row.entity_class, row.from_rating)
            ].append(row)
        object.__setattr__(
            self, "_profitability", {row.id: row for row in self.profitability_inputs}
        )
        object.__setattr__(
            self,
            "_constraints",
            {
                (row.entity_class, row.sub_class, row.rating_band, row.action_code): row
                for row in self.steering_action_constraints
            },
        )
        object.__setattr__(
            self,
            "_overlays",
            {row.jurisdiction_overlay: row for row in self.regulatory_overlay_selection},
        )
        self.validate()

    @property
    def scenario_ids(self) -> set[str]:
        """Return active scenario ids available in the package."""
        return {row.scenario_id for row in self.scenario_definitions if row.is_active}

    def validate(self) -> None:
        """Run cross-file validation for the loaded package."""
        expected_files = {*GENERATED_FILE_ORDER, "README.md", "validation_report.json"}
        missing = expected_files - set(self.manifest.generated_files)
        if missing:
            raise SteeringDomainError(
                "INPUT_PACKAGE_INCOMPLETE",
                f"Generated input package manifest is missing files: {sorted(missing)}",
                remediation="Regenerate the package with `uv run rwa-generate-missing-inputs`.",
            )
        if self.manifest.validation_status != "PASSED":
            raise SteeringDomainError(
                "INPUT_PACKAGE_NOT_VALIDATED",
                "Generated input package is not marked as validated.",
                remediation="Regenerate and validate generated steering inputs.",
            )
        self._validate_hashes()
        self._validate_references()
        self._validate_migration_totals()

    def ensure_jurisdiction(self, jurisdiction: str) -> None:
        """Raise a structured error if a request references an unknown overlay."""
        if jurisdiction not in self._overlays:
            raise SteeringDomainError(
                "UNKNOWN_JURISDICTION_OVERLAY",
                f"Unknown jurisdiction overlay {jurisdiction!r}.",
                field_path="jurisdiction",
                remediation="Use one of the overlays listed in regulatory_overlay_selection.csv.",
                context={"available": sorted(self._overlays)},
            )

    def scenario_assumption(self, scenario_id: str, projection_date: date) -> ScenarioAssumption:
        """Build a scenario assumption object from generated package rows."""
        scenario = self._scenario(scenario_id)
        macro = self.macro_for(scenario_id, projection_date)
        avg_growth = self.average_growth_rate(scenario_id, projection_date.year)
        avg_dlgd = self.average_dlgd(scenario_id, projection_date.year)
        fx_shocks = {
            row.from_ccy: row.fx_shock_pct
            for row in self.fx_scenario_rates
            if row.scenario_id == scenario_id and row.projection_date == projection_date
        }
        return ScenarioAssumption(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.scenario_name,
            regime_label=macro.regime_label,
            regime_score=macro.regime_score,
            risk_budget_multiplier=RISK_BUDGET_MULTIPLIERS.get(scenario_id, Decimal("1.00")),
            exposure_growth_rate=avg_growth,
            rating_notch_shift=self.expected_notch_shift(scenario_id),
            dlgd_multiplier=avg_dlgd[0],
            dlgd_addon=avg_dlgd[1],
            fx_shocks=fx_shocks,
            description=scenario.description,
        )

    def project_row(
        self,
        row: dict[str, Any],
        scenario_id: str,
        as_of_date: date,
        projection_date: date,
        *,
        apply_volume: bool = True,
        apply_maturity: bool = True,
        apply_rating: bool = True,
        apply_dlgd: bool = True,
        apply_fx: bool = True,
    ) -> dict[str, Any]:
        """Project one calculator input row using generated assumptions."""
        scenario_id = scenario_id.upper()
        self._scenario(scenario_id)
        years = elapsed_years(as_of_date, projection_date)
        projected = dict(row)

        current_exposure = parse_decimal(row["exposure_amount"])
        current_residual_maturity = parse_decimal(row["residual_maturity"], default=Decimal("0"))
        growth: SegmentGrowthAssumption | None = None
        if apply_volume or apply_maturity:
            growth = self.growth_for(row, scenario_id, projection_date.year)

        if apply_volume:
            assert growth is not None
            projected["exposure_amount"] = self._project_exposure(current_exposure, growth, years)

        if apply_fx:
            currency = str(row.get("exposure_ccy") or "").upper()
            fx = self.fx_for(scenario_id, projection_date, currency)
            projected["exposure_amount"] = parse_decimal(projected["exposure_amount"]) * (
                Decimal("1") + fx.fx_shock_pct
            )

        if apply_maturity:
            projected_maturity = current_residual_maturity - years
            if projected_maturity < Decimal("0"):
                if apply_volume and growth is not None and growth.renewal_rate > Decimal("0"):
                    maturity = renewed_maturity(row)
                    projected["original_maturity"] = maturity
                    projected["residual_maturity"] = maturity
                    projected["exposure_amount"] = (
                        parse_decimal(projected["exposure_amount"]) * growth.renewal_rate
                    )
                else:
                    projected["residual_maturity"] = Decimal("0")
                    projected["exposure_amount"] = Decimal("0")
            else:
                projected["residual_maturity"] = projected_maturity

        if apply_rating:
            entity_class = str(row["entity_class"])
            projected["counterparty_fcy_internal_rating"] = self.project_rating(
                scenario_id,
                projection_date.year,
                entity_class,
                str(row["counterparty_fcy_internal_rating"]),
            )
            projected["counterparty_lcy_internal_rating"] = self.project_rating(
                scenario_id,
                projection_date.year,
                entity_class,
                str(row["counterparty_lcy_internal_rating"]),
            )

        if apply_dlgd:
            dlgd = self.dlgd_for(row, scenario_id, projection_date.year)
            current_dlgd = parse_decimal(row["counterparty_dlgd"])
            projected["counterparty_dlgd"] = min(
                dlgd.cap,
                max(dlgd.floor, current_dlgd * dlgd.base_multiplier + dlgd.additive_shock),
            )

        return projected

    def growth_for(
        self, row: dict[str, Any], scenario_id: str, projection_year: int
    ) -> SegmentGrowthAssumption:
        """Return segment growth assumptions for a calculator input row."""
        key = (
            scenario_id,
            projection_year,
            str(row["entity_class"]),
            str(row["sub_class"]),
            str(row["exposure_ccy"]),
        )
        try:
            return self._growth[key]
        except KeyError as exc:
            raise self._missing_assumption_error("segment_growth_assumptions.csv", key) from exc

    def dlgd_for(
        self, row: dict[str, Any], scenario_id: str, projection_year: int
    ) -> DlgdScenarioAssumption:
        """Return DLGD projection assumptions for a calculator input row."""
        key = (scenario_id, projection_year, str(row["entity_class"]), str(row["sub_class"]))
        try:
            return self._dlgd[key]
        except KeyError as exc:
            raise self._missing_assumption_error("dlgd_scenario_assumptions.csv", key) from exc

    def fx_for(self, scenario_id: str, projection_date: date, from_ccy: str) -> FxScenarioRate:
        """Return FX assumptions for a scenario/date/currency pair."""
        key = (scenario_id, projection_date, from_ccy, "EUR")
        try:
            return self._fx[key]
        except KeyError as exc:
            raise self._missing_assumption_error("fx_scenario_rates.csv", key) from exc

    def macro_for(self, scenario_id: str, projection_date: date) -> MacroRegimeIndicator:
        """Return macro regime row for a scenario/date."""
        key = (scenario_id, projection_date)
        try:
            return self._macro[key]
        except KeyError as exc:
            raise self._missing_assumption_error("macro_regime_indicators.csv", key) from exc

    def project_rating(
        self, scenario_id: str, projection_year: int, entity_class: str, from_rating: str
    ) -> str:
        """Project a rating using scenario migration quantiles."""
        key = (scenario_id, projection_year, entity_class, from_rating)
        distribution = sorted(
            self._migration.get(key, []),
            key=lambda row: list(NCCR_RATING_GRADES).index(row.to_rating),
        )
        if not distribution:
            raise self._missing_assumption_error("rating_migration_matrix.csv", key)

        quantile = MIGRATION_QUANTILES.get(scenario_id, Decimal("0.50"))
        cumulative = Decimal("0")
        for row in distribution:
            cumulative += row.migration_probability
            if cumulative >= quantile:
                return row.to_rating
        return distribution[-1].to_rating

    def profitability_for(self, row_id: str) -> ProfitabilityInput | None:
        """Return profitability proxy for an exposure id when available."""
        return self._profitability.get(row_id)

    def constraint_for(
        self, row: dict[str, Any], action_code: str = "REDUCE_EXPOSURE"
    ) -> SteeringActionConstraint | None:
        """Return an action constraint for an exposure row and action code."""
        key = (
            str(row["entity_class"]),
            str(row["sub_class"]),
            str(row["counterparty_credit_quality_grade"]),
            action_code,
        )
        return self._constraints.get(key)

    def best_reduction_constraint(self, row: dict[str, Any]) -> SteeringActionConstraint | None:
        """Return the best allowed reduction-like action for an exposure row."""
        for action in ("REDUCE_EXPOSURE", "SELL_DOWN", "NON_RENEWAL"):
            constraint = self.constraint_for(row, action)
            if constraint is not None and constraint.is_allowed:
                return constraint
        return None

    def average_growth_rate(self, scenario_id: str, projection_year: int) -> Decimal:
        """Return average growth rate for summary-level scenario metadata."""
        values = [
            row.growth_rate
            for row in self.segment_growth_assumptions
            if row.scenario_id == scenario_id and row.projection_year == projection_year
        ]
        return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")

    def average_dlgd(self, scenario_id: str, projection_year: int) -> tuple[Decimal, Decimal]:
        """Return average DLGD multiplier and shock for summary metadata."""
        rows = [
            row
            for row in self.dlgd_scenario_assumptions
            if row.scenario_id == scenario_id and row.projection_year == projection_year
        ]
        if not rows:
            return Decimal("1"), Decimal("0")
        size = Decimal(len(rows))
        return (
            sum((row.base_multiplier for row in rows), Decimal("0")) / size,
            sum((row.additive_shock for row in rows), Decimal("0")) / size,
        )

    def expected_notch_shift(self, scenario_id: str) -> int:
        """Return a compact notching proxy for response metadata."""
        return {"BASE": 0, "DOWNSIDE": 1, "STRESS": 1, "RECOVERY": -1}.get(scenario_id, 0)

    def _scenario(self, scenario_id: str) -> ScenarioDefinition:
        """Return an active scenario definition or raise a structured error."""
        try:
            scenario = self._scenarios[scenario_id]
        except KeyError as exc:
            raise SteeringDomainError(
                "UNKNOWN_SCENARIO",
                f"Unknown scenario {scenario_id!r}.",
                field_path="scenarios",
                remediation="Use one of the scenario ids from scenario_definitions.csv.",
                context={"available": sorted(self.scenario_ids)},
            ) from exc
        if not scenario.is_active:
            raise SteeringDomainError(
                "INACTIVE_SCENARIO",
                f"Scenario {scenario_id!r} is not active.",
                field_path="scenarios",
            )
        return scenario

    def _validate_hashes(self) -> None:
        """Verify manifest hashes for generated files."""
        for file_name, expected_hash in self.manifest.file_sha256.items():
            path = self.root / file_name
            if not path.exists():
                raise SteeringDomainError(
                    "INPUT_PACKAGE_FILE_MISSING",
                    f"Generated input file is missing: {file_name}",
                    remediation="Regenerate the package with `uv run rwa-generate-missing-inputs`.",
                )
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise SteeringDomainError(
                    "INPUT_PACKAGE_HASH_MISMATCH",
                    f"Generated input file hash mismatch: {file_name}",
                    remediation="Regenerate the package or investigate local file changes.",
                    context={"expected": expected_hash, "actual": actual_hash},
                )

    def _validate_references(self) -> None:
        """Validate scenario, projection-date and overlay references across files."""
        scenarios = self.scenario_ids
        dates = {row.projection_date for row in self.forecast_calendar}
        for rows in (
            self.segment_growth_assumptions,
            self.rating_migration_matrix,
            self.dlgd_scenario_assumptions,
            self.fx_scenario_rates,
            self.macro_regime_indicators,
            self.portfolio_strategy_limits,
        ):
            for row in rows:
                if row.scenario_id not in scenarios:
                    raise SteeringDomainError(
                        "INPUT_PACKAGE_BAD_REFERENCE",
                        f"Unknown scenario reference {row.scenario_id!r}.",
                    )
                row_date = getattr(row, "projection_date", None)
                if row_date is not None and row_date not in dates:
                    raise SteeringDomainError(
                        "INPUT_PACKAGE_BAD_REFERENCE",
                        f"Unknown projection date reference {row_date!r}.",
                    )

    def _validate_migration_totals(self) -> None:
        """Ensure every migration vector sums to exactly one."""
        totals: dict[tuple[str, int, str, str], Decimal] = {}
        for row in self.rating_migration_matrix:
            key = (row.scenario_id, row.projection_year, row.entity_class, row.from_rating)
            totals[key] = totals.get(key, Decimal("0")) + row.migration_probability
        bad = {key: total for key, total in totals.items() if total != Decimal("1.000000")}
        if bad:
            first_key = next(iter(bad))
            raise SteeringDomainError(
                "INPUT_PACKAGE_BAD_MIGRATION_MATRIX",
                f"Rating migration probabilities do not sum to 1 for {first_key}.",
                context={"sum": str(bad[first_key])},
            )

    def _project_exposure(
        self, current_exposure: Decimal, growth: SegmentGrowthAssumption, years: Decimal
    ) -> Decimal:
        """Project exposure amount with generated growth and runoff assumptions."""
        growth_factor = Decimal("1") + growth.growth_rate * years
        amortization_factor = Decimal("1") - min(Decimal("1"), growth.amortization_rate * years)
        prepayment_factor = Decimal("1") - min(Decimal("1"), growth.prepayment_rate * years)
        new_origination = current_exposure * growth.new_origination_rate * years
        projected = current_exposure * growth_factor * amortization_factor * prepayment_factor
        return max(Decimal("0"), projected + new_origination)

    def _missing_assumption_error(
        self, file_name: str, key: tuple[Any, ...]
    ) -> SteeringDomainError:
        """Build a structured error for missing generated assumptions."""
        return SteeringDomainError(
            "MISSING_GENERATED_ASSUMPTION",
            f"Generated assumption not found in {file_name}.",
            remediation="Regenerate missing inputs or add the missing segment/date/scenario row.",
            context={"file": file_name, "key": [str(item) for item in key]},
        )


def load_steering_input_package(
    root: str | Path = DEFAULT_OUTPUT_ROOT,
) -> SteeringInputPackage:
    """Load and validate generated steering input files from disk."""
    root_path = Path(root)
    manifest = GeneratedInputManifest.model_validate(
        json.loads((root_path / "manifest.json").read_text(encoding="utf-8"))
    )
    return SteeringInputPackage(
        root=root_path,
        manifest=manifest,
        scenario_definitions=read_csv_models(
            root_path / "scenario_definitions.csv", ScenarioDefinition
        ),
        forecast_calendar=read_csv_models(root_path / "forecast_calendar.csv", ForecastCalendarRow),
        segment_growth_assumptions=read_csv_models(
            root_path / "segment_growth_assumptions.csv", SegmentGrowthAssumption
        ),
        rating_migration_matrix=read_csv_models(
            root_path / "rating_migration_matrix.csv", RatingMigrationRow
        ),
        dlgd_scenario_assumptions=read_csv_models(
            root_path / "dlgd_scenario_assumptions.csv", DlgdScenarioAssumption
        ),
        fx_scenario_rates=read_csv_models(root_path / "fx_scenario_rates.csv", FxScenarioRate),
        macro_regime_indicators=read_csv_models(
            root_path / "macro_regime_indicators.csv", MacroRegimeIndicator
        ),
        regulatory_overlay_selection=read_csv_models(
            root_path / "regulatory_overlay_selection.csv", RegulatoryOverlaySelection
        ),
        profitability_inputs=read_csv_models(
            root_path / "profitability_inputs.csv", ProfitabilityInput
        ),
        steering_action_constraints=read_csv_models(
            root_path / "steering_action_constraints.csv", SteeringActionConstraint
        ),
        portfolio_strategy_limits=read_csv_models(
            root_path / "portfolio_strategy_limits.csv", PortfolioStrategyLimit
        ),
        data_quality_flags=read_csv_models(root_path / "data_quality_flags.csv", DataQualityFlag),
    )


def renewed_maturity(row: dict[str, Any]) -> Decimal:
    """Return the maturity assigned to a renewed exposure in open-book forecasts.

    Closed-book projections still mature to zero. Forecast/steering projections use generated
    renewal assumptions, so a renewed product receives an operational maturity based on the
    original deal maturity, bounded to the calculator's effective one-to-five-year range.
    """
    original = parse_decimal(
        row.get("original_maturity") or row.get("residual_maturity"),
        default=Decimal("1"),
    )
    return min(max(original, Decimal("1")), Decimal("5"))


def read_csv_models[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    """Read CSV rows and validate each row with the provided Pydantic model."""
    with path.open(encoding="utf-8", newline="") as handle:
        return [model.model_validate(row) for row in csv.DictReader(handle)]
