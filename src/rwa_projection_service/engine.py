from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from rwa_calculator.paths import NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH
from rwa_calculator.rwa_calculator.calculator import RwaCalculator
from rwa_calculator.rwa_calculator.fastapi_app import CALCULATION_ENGINE_VERSION
from rwa_calculator.rwa_calculator.models import CountryInfoRecord

from .calendar import projection_dates
from .schemas import (
    OutputProjection,
    OutputSummary,
    ProjectionError,
    ProjectionRequest,
    ProjectionResponse,
)

PROJECTION_ENGINE_VERSION = "rwa-projection-alpha-0.1.0"
DAY_COUNT_DENOMINATOR = Decimal("365")
PROJECTION_VALUE_FIELDS = (
    "basel_3_0_rw_final",
    "basel_3_0_rwa",
    "basel_3_0_ro_rw",
    "basel_3_1_rw_foundation",
    "basel_3_1_rwa_foundation",
    "basel_3_1_ro_rw_foundation",
    "basel_3_1_rw_standardised",
    "basel_3_1_rwa_standardised",
    "basel_3_1_ro_rw_standardised",
)


class RwaProjectionService:
    """Projection engine treating the RWA calculator as f(x, t).

    The service does not reimplement Basel logic. It builds future views of
    each input asset by advancing time-dependent fields, primarily residual
    maturity, then delegates every point-in-time calculation to
    `rwa_calculator`.
    """

    def __init__(
        self,
        nccr_mapping_path: str | Path = NCCR_MAPPING_PATH,
        country_info_path: str | Path = PREPROD_COUNTRY_INFO_PATH,
    ) -> None:
        """Load stable reference data used by default projection requests."""
        self.nccr_mapping_path = Path(nccr_mapping_path)
        self.country_info_path = Path(country_info_path)
        self.calculator = RwaCalculator.from_files(self.nccr_mapping_path, self.country_info_path)

    def calculate(self, request: ProjectionRequest) -> ProjectionResponse:
        """Calculate base RWA and all monthly projected RWA points for a request."""
        calculator = self._calculator_for_request(request)
        dates = projection_dates(request.run_date, request.projected_months)

        base_payload = calculator.calculate_batch(request.core_info)
        projections: list[OutputProjection] = []
        errors = [
            ProjectionError(id=error["id"], messages=list(error["messages"]))
            for error in base_payload["errors"]
        ]

        for projection_date in dates:
            projections.extend(
                self._project_row(
                    calculator=calculator,
                    row=row,
                    run_date=request.run_date,
                    projection_date=projection_date,
                    errors=errors,
                )
                for row in request.core_info
            )

        return ProjectionResponse(
            regulatory_reference_version=request.regulatory_reference_version,
            calculation_engine_version=CALCULATION_ENGINE_VERSION,
            projection_engine_version=PROJECTION_ENGINE_VERSION,
            run_date=request.run_date,
            projected_months=request.projected_months,
            projection_dates=dates,
            summary=OutputSummary(
                input_data_records=len(request.core_info),
                output_successful_records=base_payload["summary"]["output_successful_records"],
                output_successful_projection_records=len(projections),
                output_failure_records=len(errors),
            ),
            results=base_payload["results"],
            projections=projections,
            errors=errors,
        )

    def _calculator_for_request(self, request: ProjectionRequest) -> RwaCalculator:
        """Return a calculator scoped to request-level country overrides if supplied."""
        if request.country_info is None:
            return self.calculator

        countries = {
            country.incorporation_country: country
            for country in (CountryInfoRecord.from_mapping(row) for row in request.country_info)
        }
        return RwaCalculator(
            nccr_mapping_path=self.calculator.nccr_mapping_path,
            countries=countries,
            nccr_mapping=self.calculator.nccr_mapping,
        )

    def _project_row(
        self,
        calculator: RwaCalculator,
        row: dict[str, Any],
        run_date: date,
        projection_date: date,
        errors: list[ProjectionError],
    ) -> OutputProjection:
        """Project one asset to one date and append row-level failures to `errors`.

        A matured asset is represented by zero RWA values. A malformed or
        recalculation-failing asset keeps the projection grid shape but returns
        empty measures, so consumers can distinguish "matured" from "failed".
        """
        row_id = str(row.get("id") or "unknown")
        residual_maturity = parse_optional_decimal(row.get("residual_maturity"))
        if residual_maturity is None:
            return empty_projection(row_id, projection_date)

        projected_maturity = residual_maturity - elapsed_years(run_date, projection_date)
        if projected_maturity < Decimal("0"):
            return zero_projection(row_id, projection_date)

        projected_row = dict(row)
        projected_row["residual_maturity"] = projected_maturity
        payload = calculator.calculate_batch([projected_row])
        if payload["errors"]:
            errors.extend(
                (
                    ProjectionError(
                        id=error["id"],
                        projection_date=projection_date,
                        messages=list(error["messages"]),
                    )
                )
                for error in payload["errors"]
            )
            return empty_projection(row_id, projection_date)

        result = payload["results"][0]
        return OutputProjection(
            id=row_id,
            projection_date=projection_date,
            **{field: result[field] for field in PROJECTION_VALUE_FIELDS},
        )


def elapsed_years(run_date: date, projection_date: date) -> Decimal:
    """Return elapsed actual/365 years between run date and projection date."""
    elapsed_days = (projection_date - run_date).days
    if elapsed_days <= 0:
        return Decimal("0")
    return Decimal(elapsed_days) / DAY_COUNT_DENOMINATOR


def parse_optional_decimal(value: Any) -> Decimal | None:
    """Parse an optional decimal-compatible input while preserving blanks as `None`."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"residual_maturity must be decimal-compatible, got {value!r}") from exc


def zero_projection(row_id: str, projection_date: date) -> OutputProjection:
    """Build a projection row for an asset that has matured before the horizon date."""
    return OutputProjection(
        id=row_id,
        projection_date=projection_date,
        **{field: Decimal("0") for field in PROJECTION_VALUE_FIELDS},
    )


def empty_projection(row_id: str, projection_date: date) -> OutputProjection:
    """Build a shape-preserving projection row when no valid RWA can be produced."""
    return OutputProjection(
        id=row_id,
        projection_date=projection_date,
        **dict.fromkeys(PROJECTION_VALUE_FIELDS),
    )


def projection_response_to_dict(response: ProjectionResponse) -> dict[str, Any]:
    """Convert a response to a plain dictionary with projection rows normalised."""
    payload = response.model_dump(mode="python")
    payload["projections"] = [asdict_projection(row) for row in response.projections]
    return payload


def asdict_projection(row: OutputProjection) -> dict[str, Any]:
    """Convert one projection model to the dictionary shape used by tests and exports."""
    return row.model_dump(mode="python")
