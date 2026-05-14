from __future__ import annotations

from decimal import Decimal

from rwa_calculator.paths import (
    NCCR_MAPPING_PATH,
    PREPROD_CORE_INFO_PATH,
    PREPROD_COUNTRY_INFO_PATH,
)
from rwa_calculator.rwa_calculator.calculator import RwaCalculator, load_core_csv


def test_calculator_golden_first_three_preprod_rows() -> None:
    """Golden regression test for representative pre-production exposure rows."""
    rows = load_core_csv(PREPROD_CORE_INFO_PATH)[:3]
    calculator = RwaCalculator.from_files(NCCR_MAPPING_PATH, PREPROD_COUNTRY_INFO_PATH)

    payload = calculator.calculate_batch(rows, include_trace=True)

    assert payload["errors"] == []
    assert [
        (
            row["id"],
            row["basel_3_1_pd"],
            row["basel_3_1_dlgd"],
            row["basel_3_1_rw_standardised"],
            row["basel_3_1_rw_final"],
            row["basel_3_1_rwa_final"],
        )
        for row in payload["results"]
    ] == [
        (
            "EXP000001",
            Decimal("0.006300"),
            Decimal("0.400000"),
            Decimal("0.500000"),
            Decimal("0.500000"),
            Decimal("19520833.47"),
        ),
        (
            "EXP000002",
            Decimal("0.003700"),
            Decimal("0.400000"),
            Decimal("0.000000"),
            Decimal("0.000000"),
            Decimal("0.00"),
        ),
        (
            "EXP000003",
            Decimal("0.001300"),
            Decimal("0.377400"),
            Decimal("0.750000"),
            Decimal("0.543750"),
            Decimal("437807.13"),
        ),
    ]
    assert payload["results"][0]["trace"][0]["step_id"] == "pd_lookup"
