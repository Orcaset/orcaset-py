# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Run the example. Scrapes TSA checkpoint volume to estimate current-quarter passenger revenue."""

from datetime import date

from model import (
    NOWCAST_QUARTER,
    QUARTER,
    nowcast_windows,
    operating_revenue_stmt,
)
from scrape import TSA_URL, tsa_passengers

from orcaset import Context, Period, fixed_width_table, isna

OUTPUT_START = date(2025, 12, 31)
OUTPUT_END = date(2026, 12, 31)


def quarter_label(day: date) -> str:
    """Label inclusive quarter-end dates. Blank the exclusive opening boundary."""
    if day <= OUTPUT_START:
        return ""
    return f"Q{(day.month - 1) // 3 + 1} {day.year}"


def main() -> None:
    ctx = Context()
    qtd, prior_qtd = ctx.get(nowcast_windows)
    current_tsa = ctx.get_at(tsa_passengers, qtd)
    prior_tsa = ctx.get_at(tsa_passengers, prior_qtd)
    if isna(current_tsa) or isna(prior_tsa):
        raise ValueError("missing TSA QTD inputs for passenger revenue")
    if prior_tsa == 0.0:
        raise ValueError("prior-quarter TSA QTD is zero")
    factor = current_tsa / prior_tsa

    print("Southwest Airlines (LUV) operating revenue")
    print("Revenue in $ millions; TSA checkpoint passengers in travelers")
    print()
    print(
        f"Estimate {quarter_label(NOWCAST_QUARTER.end)} passenger revenue "
        f"from TSA checkpoint QTD vs the prior quarter ({factor:.4f})."
    )
    print(f"Source: {TSA_URL}")
    print(f"TSA QTD {qtd.start.isoformat()} → {qtd.end.isoformat()}: {current_tsa:,.0f}")
    print(f"TSA QTD {prior_qtd.start.isoformat()} → {prior_qtd.end.isoformat()}: {prior_tsa:,.0f}")
    print()

    quarters = Period.list(OUTPUT_START, QUARTER, OUTPUT_END)
    result = operating_revenue_stmt.values_for_periods(ctx, quarters)
    table = fixed_width_table(
        result,
        date_formatter=quarter_label,
        value_formatter=lambda value: "" if value is None else f"{value:,.0f}",
    )
    # Display only the quarter-end header.
    _start, end_header, *body = table.splitlines()
    if not end_header.startswith("End"):
        raise RuntimeError("expected End header from fixed_width_table")
    print("\n".join((f"   {end_header[3:]}".rstrip(), *body)))


if __name__ == "__main__":
    main()
