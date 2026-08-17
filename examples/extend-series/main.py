# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Horizontal composition of a finite historical series and a later forecast.

``hist_revenue`` is the left-hand base (quarterly, ``covered``). ``revenue``
appends a monthly continuation that starts at the last historical end. Queries
that stay inside history never materialize the forecast; queries after the
seam use only the continuation; queries that cross the last historical end are
split and added.
"""

import operator
from collections.abc import Iterator
from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    CellFactory,
    Context,
    Maybe,
    Period,
    PeriodExtendSeries,
    PeriodSeries,
    Step,
    Stmt,
    accrual,
    covered,
    fixed_width_table,
    get_at,
    isna,
    map2_some,
)

MONTHLY = relativedelta(months=1)

HISTORICAL: list[tuple[Period, float]] = [
    (Period(date(2025, 1, 1), date(2025, 4, 1)), 300.0),
    (Period(date(2025, 4, 1), date(2025, 7, 1)), 330.0),
    (Period(date(2025, 7, 1), date(2025, 10, 1)), 363.0),
]


@PeriodSeries.define("hist_revenue", covered)
def hist_revenue() -> Iterator[tuple[Period, float]]:
    yield from HISTORICAL


@PeriodExtendSeries.define("revenue", hist_revenue, map2_some(operator.add))
def revenue(last: Period) -> PeriodSeries[Maybe[float]]:
    def cells() -> Iterator[tuple[Period, CellFactory[float]]]:
        for k in Period.seq(last.end, MONTHLY):

            def factory(p: Period = k) -> Step[float]:
                if p.start == last.end:
                    prior = yield from get_at(hist_revenue, last)
                    if isna(prior):
                        raise ValueError(f"missing last historical revenue {last}")
                    run_rate = (
                        prior * YF.cmonthly(p.start, p.end) / YF.cmonthly(last.start, last.end)
                    )
                    return run_rate * 1.01
                prior = yield from get_at(forecast, p.from_start(-MONTHLY))
                if isna(prior):
                    raise ValueError(f"missing prior forecast revenue for {p}")
                return prior * 1.01

            yield k, factory

    forecast = PeriodSeries("forecast_revenue", cells, accrual(YF.cmonthly))
    return forecast


ctx = Context()
quarters = [p for p, _ in HISTORICAL]
forecast_months = list(islice(Period.seq(date(2025, 10, 1), MONTHLY), 3))


def show(value: Maybe[float] | float) -> str:
    return "Na" if isna(value) else f"{value:.4f}"


print("Left of seam (historical quarters)")
for q in quarters:
    print(f"  {q}: {show(ctx.get_at(revenue, q))}")

intra = Period(date(2025, 9, 1), date(2025, 10, 1))
print(f"\nPartial historical period stays Na ({intra}): {show(ctx.get_at(revenue, intra))}")

print("\nRight of seam (monthly projection, 1% growth off last-quarter run-rate)")
for q in forecast_months:
    print(f"  {q}: {show(ctx.get_at(revenue, q))}")

projected_quarter = Period(forecast_months[0].start, forecast_months[-1].end)
quarterly_statement = Stmt(revenue).values_for_periods(
    ctx,
    [*quarters, projected_quarter],
)

print("\nOne composed row")
print(fixed_width_table(quarterly_statement))

aligned = Period(date(2025, 7, 1), date(2025, 12, 1))
print(f"\nDeps: revenue @ {aligned} (query crosses the seam)\n")
print(ctx.dependencies(revenue, aligned))
