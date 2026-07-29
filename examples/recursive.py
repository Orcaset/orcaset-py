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
    flow,
    isna,
    period_union,
)

MONTHLY = relativedelta(months=1)
QUARTERLY = relativedelta(months=3)


def revenue_at(s: CellReader[Period, float], key: Period) -> Step[float]:
    """Grid definition as a recurrence: each cell is the prior cell grown."""
    prior = yield from s.cell(key.shift(-MONTHLY))
    return 100.0 if isna(prior) else prior * 1.01


revenue = flow(
    "revenue",
    lambda: Period.seq(date(2026, 1, 1), MONTHLY),
    revenue_at,
    yf=YF.cmonthly,
)

cogs = revenue.map("costs", lambda r: r * -0.5 if not isna(r) else Na)


def opex_at(s: CellReader[Period, float], key: Period) -> Step[float]:
    """Grid definition as a recurrence: each cell is the prior cell grown."""
    prior = yield from s.cell(key.shift(-QUARTERLY))
    return -25.0 if isna(prior) else prior * 1.01


opex = flow(
    "opex",
    lambda: Period.seq(date(2026, 1, 1), QUARTERLY),
    opex_at,
    yf=YF.cmonthly,
)


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
