from __future__ import annotations

import calendar
from datetime import date


def month_end(value: date) -> date:
    """Return the last calendar day of value's month."""
    return date(value.year, value.month, calendar.monthrange(value.year, value.month)[1])


def add_months(value: date, months: int) -> date:
    """Add calendar months while preserving a valid day in the target month."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def projection_dates(run_date: date, projected_months: int) -> list[date]:
    """Build t0 plus month-end projection dates t1..tN."""
    dates = [run_date]
    current_month_start = date(run_date.year, run_date.month, 1)
    dates.extend(
        month_end(add_months(current_month_start, offset)) for offset in range(projected_months)
    )
    return dates
