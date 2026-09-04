# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Extend a seris of quarterly historicals with a monthly forecaset."""

from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Cell,
    Cells,
    Cons,
    Context,
    Effect,
    Maybe,
    Period,
    Rule,
    Series,
    Stmt,
    accrue,
    fixed_width_table,
    get,
    isna,
)

MONTHLY = relativedelta(months=1)
MONTHLY_GROWTH_RATE = 0.10

# ---- Historical series ----
HISTORICAL = [
    (Period(date(2025, 1, 1), date(2025, 4, 1)), 300.0),
    (Period(date(2025, 4, 1), date(2025, 7, 1)), 330.0),
    (Period(date(2025, 7, 1), date(2025, 10, 1)), 363.0),
]

accrue_monthly = accrue(YF.cmonthly)
hist_revenue = Series.of("hist_revenue", accrue_monthly, HISTORICAL)


# ---- Forecast series ----
def grow(period: Period, prior: Rule[float]) -> Cells[Period, float]:

    def node() -> Cons[Period, float]:
        def value() -> Effect[float]:
            return (yield from get(prior)) * (1 + MONTHLY_GROWTH_RATE)

        this = Cell(f"forecast_revenue@{period}", value)
        return Cons(period, this, grow(period.from_end(MONTHLY), this))

    return Cell(f"forecast_revenue.tail@{period}", node, structural=True)


def forecast_cells(last: Cons[Period, float] | None) -> Cells[Period, float]:
    # If there is no history, terminate without any forecast cells.
    if last is None:
        return Cell("forecast_revenue.cells", lambda: None, structural=True)

    # The first forecast month is the last historical period's end plus one month.
    first = last.key.from_end(MONTHLY)

    def run_rate() -> Effect[float]:
        quarter = yield from get(last.cell)
        return (
            quarter
            * YF.cmonthly(first.start, first.end)
            / YF.cmonthly(last.key.start, last.key.end)
        )

    return grow(first, Cell("forecast_revenue.run_rate", run_rate))


revenue = Series.extend("revenue", accrue_monthly, base=hist_revenue.cells, cont=forecast_cells)


# ---- Output ----
ctx = Context()
quarters = [period for period, _ in HISTORICAL]
forecast_months = list(islice(Period.seq(date(2025, 10, 1), MONTHLY), 3))


def show(value: Maybe[float] | float) -> str:
    return "Na" if isna(value) else f"{value:.4f}"


print("Left of seam (historical quarters)")
for quarter in quarters:
    print(f"  {quarter}: {show(ctx.get_at(revenue, quarter))}")

intra = Period(date(2025, 9, 1), date(2025, 10, 1))
print(f"\nPartial historical period is prorated ({intra}): {show(ctx.get_at(revenue, intra))}")

print("\nRight of seam (monthly projection, 10% growth off the prior month)")
for month in forecast_months:
    print(f"  {month}: {show(ctx.get_at(revenue, month))}")

projected_quarter = Period(forecast_months[0].start, forecast_months[-1].end)
quarterly_statement = Stmt(revenue).values_for_periods(ctx, [*quarters, projected_quarter])

print("\nOne composed row")
print(fixed_width_table(quarterly_statement))

aligned = Period(date(2025, 7, 1), date(2025, 12, 1))
print(f"\nDeps: revenue @ {aligned} (query crosses the seam)\n")
print(ctx.dependencies(revenue, aligned))
