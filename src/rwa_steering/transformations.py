from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from rwa_calculator.rwa_pydantic_schemas import NCCR_RATING_GRADES
from rwa_projection_service.engine import elapsed_years

from .scenarios import ScenarioAssumption


def parse_decimal(value: Any, default: Decimal | None = None) -> Decimal:
    """Parse calculator-style scalar values into ``Decimal``.

    Calculator inputs and outputs can arrive as strings, decimals or occasionally empty
    strings from CSV records. Steering code keeps all financial arithmetic in Decimal to
    avoid float drift in RWA deltas and recommendation scores.
    """

    if value is None or (isinstance(value, str) and value.strip() == ""):
        if default is None:
            raise ValueError("Decimal value is required")
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Value {value!r} is not decimal-compatible") from exc


def migrate_rating(grade: Any, notch_shift: int) -> str:
    """Move an NCCR rating up or down the known calculator rating scale.

    Positive ``notch_shift`` deteriorates credit quality; negative values improve it.
    The result is clipped at the best and worst supported grades so scenario shocks never
    produce a rating outside the schema accepted by ``rwa_calculator``.
    """

    grade_text = str(grade).strip()
    scale = list(NCCR_RATING_GRADES)
    current_index = scale.index(grade_text)
    projected_index = min(max(current_index + notch_shift, 0), len(scale) - 1)
    return scale[projected_index]


def project_row(
    row: dict[str, Any],
    scenario: ScenarioAssumption,
    as_of_date: date,
    projection_date: date,
    *,
    apply_volume: bool = True,
    apply_maturity: bool = True,
    apply_rating: bool = True,
    apply_dlgd: bool = True,
    apply_fx: bool = True,
) -> dict[str, Any]:
    """Project one calculator input row to a future scenario/date.

    This is the central adapter between steering assumptions and the deterministic RWA
    calculator. It forecasts calculator inputs rather than final RWA, preserving auditability:
    every projected row can be validated and passed through the same proxy calculator path as the
    current portfolio.

    The ``apply_*`` switches support sequential revaluation attribution. For example, the
    attribution layer can set only ``apply_rating=True`` to isolate the first-order rating
    migration impact while leaving volume, maturity, DLGD and FX unchanged.
    """

    years = elapsed_years(as_of_date, projection_date)
    projected = dict(row)

    current_exposure = parse_decimal(row["exposure_amount"])
    current_residual_maturity = parse_decimal(row["residual_maturity"], default=Decimal("0"))

    if apply_volume:
        growth_factor = Decimal("1") + scenario.exposure_growth_rate * years
        projected["exposure_amount"] = max(Decimal("0"), current_exposure * growth_factor)

    if apply_fx:
        currency = str(row.get("exposure_ccy") or "").upper()
        fx_factor = Decimal("1") + scenario.fx_shocks.get(currency, Decimal("0"))
        projected["exposure_amount"] = parse_decimal(projected["exposure_amount"]) * fx_factor

    if apply_maturity:
        projected_maturity = current_residual_maturity - years
        if projected_maturity < Decimal("0"):
            projected["residual_maturity"] = Decimal("0")
            projected["exposure_amount"] = Decimal("0")
        else:
            projected["residual_maturity"] = projected_maturity

    if apply_rating:
        projected["counterparty_fcy_internal_rating"] = migrate_rating(
            row["counterparty_fcy_internal_rating"], scenario.rating_notch_shift
        )
        projected["counterparty_lcy_internal_rating"] = migrate_rating(
            row["counterparty_lcy_internal_rating"], scenario.rating_notch_shift
        )

    if apply_dlgd:
        current_dlgd = parse_decimal(row["counterparty_dlgd"])
        projected["counterparty_dlgd"] = min(
            Decimal("1"), current_dlgd * scenario.dlgd_multiplier + scenario.dlgd_addon
        )

    return projected
