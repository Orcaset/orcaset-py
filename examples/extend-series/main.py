# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Append a monthly forecast to a finite quarterly history."""

from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Context,
    Maybe,
    Period,
    Series,
    Step,
    Stmt,
    Thunk,
    covered,
    fixed_width_table,
    get_at,
    isna,
)

MONTHLY = relativedelta(months=1)
HISTORICAL: list[tuple[Period, float]] = [
    (Period(date(2025, 1, 1), date(2025, 4, 1)), 300.0),
    (Period(date(2025, 4, 1), date(2025, 7, 1)), 330.0),
    (Period(date(2025, 7, 1), date(2025, 10, 1)), 363.0),
]

hist_revenue = Series.of("hist_revenue", covered, HISTORICAL)


def forecast_cells(last: Period | None):
    if last is None:
        raise ValueError("revenue history must not be empty")

    def step(period: Period) -> tuple[Period, Thunk[float], Period]:
        def value() -> Step[float]:
            if period.start == last.end:
                prior = yield from get_at(hist_revenue, last)
                if isna(prior):
                    raise ValueError(f"missing last historical revenue {last}")
                run_rate = (
                    prior
                    * YF.cmonthly(period.start, period.end)
                    / YF.cmonthly(last.start, last.end)
                )
                return run_rate * 1.01
            prior = yield from get_at(forecast, period.from_start(-MONTHLY))
            if isna(prior):
                raise ValueError(f"missing prior forecast revenue for {period}")
            return prior * 1.01

        return period, Thunk(value), period.from_end(MONTHLY)

    forecast = Series.unfold(
        "forecast_revenue",
        covered,
        seed=next(Period.seq(last.end, MONTHLY)),
        step=step,
    )
    return forecast.cells


revenue = Series.extend(
    "revenue",
    covered,
    base=hist_revenue.cells,
    cont=forecast_cells,
)

ctx = Context()
quarters = [period for period, _ in HISTORICAL]
forecast_months = list(islice(Period.seq(date(2025, 10, 1), MONTHLY), 3))


def show(value: Maybe[float] | float) -> str:
    return "Na" if isna(value) else f"{value:.4f}"


print("Left of seam (historical quarters)")
for quarter in quarters:
    print(f"  {quarter}: {show(ctx.get_at(revenue, quarter))}")

intra = Period(date(2025, 9, 1), date(2025, 10, 1))
print(f"\nPartial historical period stays Na ({intra}): {show(ctx.get_at(revenue, intra))}")

print("\nRight of seam (monthly projection, 1% growth off last-quarter run-rate)")
for month in forecast_months:
    print(f"  {month}: {show(ctx.get_at(revenue, month))}")

projected_quarter = Period(forecast_months[0].start, forecast_months[-1].end)
quarterly_statement = Stmt(revenue).values_for_periods(ctx, [*quarters, projected_quarter])

print("\nOne composed row")
print(fixed_width_table(quarterly_statement))

aligned = Period(date(2025, 7, 1), date(2025, 12, 1))
print(f"\nDeps: revenue @ {aligned} (query crosses the seam)\n")
print(ctx.dependencies(revenue, aligned))
