from __future__ import annotations

from datetime import date

from rwa_projection_service.calendar import projection_dates


def test_projection_dates_from_mid_month() -> None:
    assert projection_dates(date(2025, 12, 16), 3) == [
        date(2025, 12, 16),
        date(2025, 12, 31),
        date(2026, 1, 31),
        date(2026, 2, 28),
    ]


def test_projection_dates_when_t0_is_month_end() -> None:
    assert projection_dates(date(2025, 12, 31), 3) == [
        date(2025, 12, 31),
        date(2025, 12, 31),
        date(2026, 1, 31),
        date(2026, 2, 28),
    ]


def test_projection_dates_from_first_day_of_month() -> None:
    assert projection_dates(date(2026, 1, 1), 3) == [
        date(2026, 1, 1),
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
    ]
