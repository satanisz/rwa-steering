from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from .discussion_schemas import RwaInputRecord, RwaOutputRecord, ValidationFlag

_FORMULA_TOLERANCE = Decimal("0.0001")
_ABSOLUTE_TOLERANCE = Decimal("1.00")


def detect_portfolio_input_anomalies(
    rwa_input_data: list[RwaInputRecord],
    rwa_output_results: list[RwaOutputRecord],
) -> list[ValidationFlag]:
    """Detect structural input/output anomalies without delegating math to an LLM."""
    flags: list[ValidationFlag] = []
    input_ids = [record.asset_id for record in rwa_input_data]
    output_ids = [record.asset_id for record in rwa_output_results]

    for asset_id, count in Counter(input_ids).items():
        if count > 1:
            flags.append(
                ValidationFlag(
                    code="DUPLICATE_INPUT_ASSET",
                    severity="MATERIAL",
                    asset_id=asset_id,
                    source_agent="DataAnalystAgent",
                    message=f"Asset {asset_id} appears {count} times in input data.",
                    requires_human_intervention=True,
                )
            )

    output_id_set = set(output_ids)
    for record in rwa_input_data:
        if record.exposure_amount <= 0:
            flags.append(
                ValidationFlag(
                    code="NON_POSITIVE_EXPOSURE",
                    severity="MATERIAL",
                    asset_id=record.asset_id,
                    source_agent="DataAnalystAgent",
                    message=f"Asset {record.asset_id} has non-positive exposure amount.",
                    requires_human_intervention=True,
                )
            )
        if record.risk_weight is None:
            flags.append(
                ValidationFlag(
                    code="MISSING_INPUT_RISK_WEIGHT",
                    severity="WATCH",
                    asset_id=record.asset_id,
                    source_agent="DataAnalystAgent",
                    message=f"Asset {record.asset_id} has no input risk weight parameter.",
                )
            )
        if record.rating is None or not record.rating:
            flags.append(
                ValidationFlag(
                    code="MISSING_RATING",
                    severity="WATCH",
                    asset_id=record.asset_id,
                    source_agent="DataAnalystAgent",
                    message=f"Asset {record.asset_id} has no rating or risk bucket.",
                )
            )
        if record.validation_status and record.validation_status.upper() not in {
            "PASSED",
            "VALID",
            "OK",
        }:
            flags.append(
                ValidationFlag(
                    code="FAILED_VALIDATION_RECORD",
                    severity="MATERIAL",
                    asset_id=record.asset_id,
                    source_agent="DataAnalystAgent",
                    message=(
                        f"Asset {record.asset_id} has validation status {record.validation_status}."
                    ),
                    requires_human_intervention=True,
                )
            )
        if record.pd is not None and record.pd > Decimal("0.20"):
            flags.append(
                ValidationFlag(
                    code="PD_OUTLIER",
                    severity="WATCH",
                    asset_id=record.asset_id,
                    source_agent="DataAnalystAgent",
                    message=f"Asset {record.asset_id} has PD above 20%.",
                )
            )
        if record.lgd is not None and record.lgd > Decimal("0.80"):
            flags.append(
                ValidationFlag(
                    code="LGD_OUTLIER",
                    severity="WATCH",
                    asset_id=record.asset_id,
                    source_agent="DataAnalystAgent",
                    message=f"Asset {record.asset_id} has LGD above 80%.",
                )
            )
        if record.asset_id not in output_id_set:
            flags.append(
                ValidationFlag(
                    code="MISSING_CALCULATOR_OUTPUT",
                    severity="CRITICAL",
                    asset_id=record.asset_id,
                    source_agent="DataAnalystAgent",
                    message=f"Asset {record.asset_id} has input data but no calculator output.",
                    requires_human_intervention=True,
                )
            )

    input_id_set = set(input_ids)
    flags.extend(
        ValidationFlag(
            code="OUTPUT_WITHOUT_INPUT",
            severity="CRITICAL",
            asset_id=record.asset_id,
            source_agent="DataAnalystAgent",
            message=f"Asset {record.asset_id} has calculator output without input data.",
            requires_human_intervention=True,
        )
        for record in rwa_output_results
        if record.asset_id not in input_id_set
    )

    return flags


def summarize_rwa_movement_drivers(
    rwa_input_data: list[RwaInputRecord],
    rwa_output_results: list[RwaOutputRecord],
) -> dict[str, Decimal | int | str]:
    """Summarize RWA movement drivers using deterministic grouped calculations."""
    inputs_by_id = {record.asset_id: record for record in rwa_input_data}
    movement_rows = [
        (
            output,
            output.rwa_amount - output.previous_rwa_amount,
            inputs_by_id.get(output.asset_id),
        )
        for output in rwa_output_results
        if output.previous_rwa_amount is not None
    ]
    total_delta = sum((delta for _output, delta, _source in movement_rows), Decimal("0"))
    absolute_delta = sum((abs(delta) for _output, delta, _source in movement_rows), Decimal("0"))
    sector_delta: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    rating_migrations = 0
    for output, delta, source in movement_rows:
        sector = output.sector or (source.sector if source is not None else None) or "Unclassified"
        sector_delta[sector] += delta
        current_rating = output.rating or (source.rating if source is not None else None)
        if output.previous_rating and current_rating and output.previous_rating != current_rating:
            rating_migrations += 1

    top_sector, top_sector_delta = _largest_abs_bucket(sector_delta)
    return {
        "movement_record_count": len(movement_rows),
        "total_rwa_delta": total_delta,
        "absolute_rwa_delta": absolute_delta,
        "top_movement_sector": top_sector,
        "top_movement_sector_delta": top_sector_delta,
        "rating_migration_count": rating_migrations,
    }


def validate_rwa_formula_deterministically(
    rwa_input_data: list[RwaInputRecord],
    rwa_output_results: list[RwaOutputRecord],
    *,
    materiality_threshold: Decimal,
) -> list[ValidationFlag]:
    """Validate reported RWA as exposure times risk weight using deterministic Python code."""
    flags: list[ValidationFlag] = []
    inputs_by_id = {record.asset_id: record for record in rwa_input_data}

    for output in rwa_output_results:
        source_input = inputs_by_id.get(output.asset_id)
        if source_input is None:
            continue
        exposure = (
            output.exposure_amount
            if output.exposure_amount is not None
            else source_input.exposure_amount
        )
        risk_weight = (
            output.risk_weight if output.risk_weight is not None else source_input.risk_weight
        )
        if risk_weight is None:
            flags.append(
                ValidationFlag(
                    code="RWA_FORMULA_PARAMETERS_MISSING",
                    severity="WATCH",
                    asset_id=output.asset_id,
                    source_agent="RiskExpertAgent",
                    message=(
                        f"Asset {output.asset_id} cannot be formula-validated because "
                        "risk weight is missing."
                    ),
                )
            )
            continue

        expected_rwa = exposure * risk_weight
        tolerance = max(abs(expected_rwa) * _FORMULA_TOLERANCE, _ABSOLUTE_TOLERANCE)
        difference = output.rwa_amount - expected_rwa
        if abs(difference) <= tolerance:
            continue

        relative_difference = _relative_difference(difference, expected_rwa)
        severity = "CRITICAL" if abs(relative_difference) >= materiality_threshold else "MATERIAL"
        flags.append(
            ValidationFlag(
                code="RWA_FORMULA_DEVIATION",
                severity=severity,
                asset_id=output.asset_id,
                source_agent="RiskExpertAgent",
                message=(
                    f"Asset {output.asset_id} reported RWA differs from deterministic "
                    f"exposure-weight validation by {difference:.2f}."
                ),
                requires_human_intervention=severity == "CRITICAL",
            )
        )

    return flags


def summarize_portfolio_structure(
    rwa_input_data: list[RwaInputRecord],
    rwa_output_results: list[RwaOutputRecord],
) -> dict[str, Decimal | int | str]:
    """Return deterministic portfolio totals and largest concentration facts."""
    total_exposure = sum((record.exposure_amount for record in rwa_input_data), Decimal("0"))
    total_rwa = sum((record.rwa_amount for record in rwa_output_results), Decimal("0"))
    by_asset_class: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_sector: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for record in rwa_input_data:
        by_asset_class[record.asset_class] += record.exposure_amount
        if record.sector:
            by_sector[record.sector] += record.exposure_amount

    largest_asset_class, largest_asset_class_exposure = _largest_bucket(by_asset_class)
    largest_sector, largest_sector_exposure = _largest_bucket(by_sector)
    rwa_density = total_rwa / total_exposure if total_exposure else Decimal("0")

    return {
        "input_record_count": len(rwa_input_data),
        "output_record_count": len(rwa_output_results),
        "asset_class_count": len(by_asset_class),
        "sector_count": len(by_sector),
        "total_exposure": total_exposure,
        "total_rwa": total_rwa,
        "rwa_density": rwa_density,
        "largest_asset_class": largest_asset_class,
        "largest_asset_class_share": _share(largest_asset_class_exposure, total_exposure),
        "largest_sector": largest_sector,
        "largest_sector_share": _share(largest_sector_exposure, total_exposure),
    }


def concentration_flags(
    portfolio_summary: dict[str, Decimal | int | str],
) -> list[ValidationFlag]:
    """Flag high concentration levels using deterministic thresholds."""
    flags: list[ValidationFlag] = []
    asset_class_share = Decimal(str(portfolio_summary["largest_asset_class_share"]))
    sector_share = Decimal(str(portfolio_summary["largest_sector_share"]))
    if asset_class_share >= Decimal("0.75"):
        flags.append(
            ValidationFlag(
                code="ASSET_CLASS_CONCENTRATION",
                severity="WATCH",
                source_agent="DataAnalystAgent",
                message=(
                    f"{portfolio_summary['largest_asset_class']} represents "
                    f"{asset_class_share * Decimal('100'):.1f}% of exposure."
                ),
            )
        )
    if sector_share >= Decimal("0.75"):
        flags.append(
            ValidationFlag(
                code="SECTOR_CONCENTRATION",
                severity="WATCH",
                source_agent="DataAnalystAgent",
                message=(
                    f"{portfolio_summary['largest_sector']} represents "
                    f"{sector_share * Decimal('100'):.1f}% of exposure."
                ),
            )
        )
    return flags


def _largest_bucket(values: defaultdict[str, Decimal]) -> tuple[str, Decimal]:
    if not values:
        return "Not available", Decimal("0")
    return max(values.items(), key=lambda item: item[1])


def _largest_abs_bucket(values: defaultdict[str, Decimal]) -> tuple[str, Decimal]:
    if not values:
        return "Not available", Decimal("0")
    return max(values.items(), key=lambda item: abs(item[1]))


def _share(value: Decimal, total: Decimal) -> Decimal:
    return value / total if total else Decimal("0")


def _relative_difference(difference: Decimal, expected: Decimal) -> Decimal:
    denominator = abs(expected) if expected else Decimal("1")
    return difference / denominator
