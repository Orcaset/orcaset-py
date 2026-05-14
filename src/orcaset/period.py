# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

type Period = tuple[date, date]


def validate_period(period: Period) -> None:
    start, end = period
    if start >= end:
        raise ValueError(f"Period start must be before end: {period!r}")


def add_months_month_end(dt: date, months: int) -> date:
    """Advance dates while preserving month-end behavior."""

    return dt + relativedelta(months=months, day=31)


def periods_by_months(start: date, end: date, months: int) -> list[Period]:
    if months <= 0:
        raise ValueError("months must be positive")
    if start >= end:
        return []

    periods: list[Period] = []
    cursor = start
    while cursor < end:
        next_date = add_months_month_end(cursor, months)
        if next_date > end:
            next_date = end
        periods.append((cursor, next_date))
        cursor = next_date
    return periods
