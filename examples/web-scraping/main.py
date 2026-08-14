# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Run the web-scraping nowcast and print a quarterly operating-revenue table."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from model import (
    NOWCAST_QUARTER,
    QUARTER,
    operating_revenue_stmt,
    qtd_windows,
    tsa_qtd_factor,
)
from scrape import TSA_URL, tsa_passengers

from orcaset import Context, Period, fixed_width_table, isna

OUTPUT_START = date(2024, 12, 31)
EASTERN = ZoneInfo("America/New_York")


def as_of_date() -> date:
    return datetime.now(EASTERN).date()


def quarter_label(day: date) -> str:
    return f"Q{(day.month - 1) // 3 + 1} {day.year}"


def reporting_quarters(today: date) -> list[Period]:
    """Q1 2025 through Q4 of the next calendar (fiscal) year after ``today``."""
    return Period.list(OUTPUT_START, QUARTER, date(today.year + 1, 12, 31))


def nowcast_windows(ctx: Context) -> tuple[Period, Period]:
    days = list(ctx.get(tsa_passengers.keys()))
    if not days:
        raise RuntimeError("TSA checkpoint series is empty")
    return qtd_windows(NOWCAST_QUARTER, days[-1].end)


def _format_millions(value: float | None) -> str:
    return "" if value is None else f"{value:,.0f}"


def main() -> None:
    today = as_of_date()
    ctx = Context()
    qtd, prior_qtd = nowcast_windows(ctx)
    current_tsa = ctx.get_at(tsa_passengers, qtd)
    prior_tsa = ctx.get_at(tsa_passengers, prior_qtd)
    factor = ctx.get_at(tsa_qtd_factor, NOWCAST_QUARTER)
    if isna(current_tsa) or isna(prior_tsa) or isna(factor):
        raise RuntimeError("TSA QTD volumes are missing; cannot nowcast")

    print("Southwest Airlines (LUV) operating revenue")
    print("$ millions")
    print()
    print(
        f"Nowcast {quarter_label(NOWCAST_QUARTER.end)} passenger revenue "
        f"from TSA checkpoint QTD vs the prior quarter ({factor:.4f})."
    )
    print(f"Source: {TSA_URL}")
    print(f"TSA QTD {qtd.start.isoformat()} → {qtd.end.isoformat()}: {current_tsa:,.0f}")
    print(f"TSA QTD {prior_qtd.start.isoformat()} → {prior_qtd.end.isoformat()}: {prior_tsa:,.0f}")
    print()

    result = operating_revenue_stmt.values_for_periods(ctx, reporting_quarters(today))
    print(fixed_width_table(result, date_formatter=quarter_label, value_formatter=_format_millions))


if __name__ == "__main__":
    main()
