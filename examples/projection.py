# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Quarterly history extended by a monthly growth projection on one spine."""

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
    Series,
    Step,
    Stmt,
    accrual,
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


@Series.define("revenue", accrual(YF.cmonthly))
def revenue() -> Iterator[tuple[Period, float | CellFactory[float]]]:
    last: Period | None = None
    for period, value in HISTORICAL:
        last = period
        yield period, value

    if last is None:
        return

    for k in Period.seq(last.end, MONTHLY):

        def factory(p: Period = k) -> Step[float]:
            prior = yield from get_at(revenue, p.from_start(-MONTHLY))
            return prior * 1.01 if not isna(prior) else 0.0

        yield k, factory


ctx = Context()

quarters = [p for p, _ in HISTORICAL]
last_hist_month = Period(date(2025, 9, 1), date(2025, 10, 1))
forecast = list(islice(Period.seq(date(2025, 10, 1), MONTHLY), 3))


def show(value: Maybe[float] | float) -> str:
    return "Na" if isna(value) else f"{value:.4f}"


print("Historical quarters")
for q in quarters:
    print(f"  {q}: {show(ctx.get_at(revenue, q))}")

print(f"\nLast historical month via accrual: {last_hist_month}")
print(f"  {show(ctx.get_at(revenue, last_hist_month))}")

print("\nMonthly projection (1% growth off one-month lookback)")
for q in forecast:
    print(f"  {q}: {show(ctx.get_at(revenue, q))}")

projected_quarter = Period(forecast[0].start, forecast[-1].end)
quarterly_statement = Stmt(revenue).values_for_periods(
    ctx,
    [*quarters, projected_quarter],
)

print("\nQuarterly statement")
print(fixed_width_table(quarterly_statement))

print(f"\nDeps: revenue @ {forecast[0]}\n")
print(ctx.dependencies(revenue, forecast[0]))
