from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    CellReader,
    Context,
    MapNSeries,
    Na,
    Period,
    Step,
    add_values,
    grid,
    isna,
    overlapping,
    period_union,
    prorated,
)

MONTHLY = relativedelta(months=1)
QUARTERLY = relativedelta(months=3)


@grid(
    lambda: Period.seq(date(2026, 1, 1), MONTHLY),
    overlapping,
    prorated(YF.cmonthly),
    "revenue",
)
def revenue(s: CellReader[Period, float], key: Period) -> Step[float]:
    """Grid definition as a recurrence: each cell is the prior cell grown."""
    prior = yield from s.cell(key.shift(-MONTHLY))
    return 100.0 if isna(prior) else prior * 1.01


cogs = revenue.map("costs", lambda r: r * -0.5 if not isna(r) else Na)


@grid(
    lambda: Period.seq(date(2026, 1, 1), QUARTERLY),
    overlapping,
    prorated(YF.cmonthly),
    "opex",
)
def opex(s: CellReader[Period, float], key: Period) -> Step[float]:
    """Grid definition as a recurrence: each cell is the prior cell grown."""
    prior = yield from s.cell(key.shift(-QUARTERLY))
    return -25.0 if isna(prior) else prior * 1.01


profit = MapNSeries(
    "profit",
    (revenue, cogs, opex),
    add_values,
    merge_keys=period_union,
)

ctx = Context()
print(ctx.demand(revenue, Period(date(2026, 1, 1), date(2026, 2, 1))))
print(ctx.demand(revenue, Period(date(2026, 2, 1), date(2026, 3, 1))))
print(ctx.demand(revenue, Period(date(2027, 3, 1), date(2027, 4, 1))))
print(ctx.dependencies(revenue, Period(date(2026, 3, 1), date(2026, 4, 1))))

print(ctx.demand(cogs, Period(date(2027, 3, 1), date(2027, 4, 1))))
print(ctx.demand(opex, Period(date(2027, 3, 1), date(2027, 4, 1))))
print(ctx.demand(profit, Period(date(2027, 3, 1), date(2027, 4, 1))))
