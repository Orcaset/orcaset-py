from collections.abc import Iterable, Iterator
from datetime import date
from itertools import repeat

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    CellFactory,
    Context,
    GridSeries,
    MapNSeries,
    Period,
    Step,
    accrual,
    add_values,
    get_at,
    isna,
    map2_some,
    map_some,
    period_union,
)

MONTHLY = relativedelta(months=1)


@GridSeries.define("revenue", accrual(YF.cmonthly))
def revenue() -> Iterable[tuple[Period, float | CellFactory[float]]]:
    """Each cell is the prior period's answer grown by 1%; seed is 100."""

    def cells() -> Iterator[tuple[Period, float | CellFactory[float]]]:
        periods = Period.seq(date(2026, 1, 1), MONTHLY)
        yield (next(periods), 100.0)

        for k in periods:

            def factory(p: Period = k) -> Step[float]:
                value = yield from get_at(revenue, p.from_start(-MONTHLY))
                return value * 1.01 if not isna(value) else 0.0

            yield k, factory

    return cells()


cogs = revenue.map("cogs", map_some(lambda r: r * -0.5))

gross_profit = revenue.map2(
    "gross_profit",
    cogs,
    map2_some(lambda r, c: r + c),
    merge_keys=period_union,
)

rd = GridSeries(
    "r&d",
    lambda: zip(Period.seq(date(2026, 1, 1), MONTHLY), repeat(-10.0)),
    accrual(YF.cmonthly),
)
sga = GridSeries(
    "sga",
    lambda: zip(Period.seq(date(2026, 1, 1), MONTHLY), repeat(-10.0)),
    accrual(YF.cmonthly),
)

income = MapNSeries(
    "income",
    (gross_profit, rd, sga),
    add_values,
    merge_keys=period_union,
)

ctx = Context()
q = Period(date(2027, 3, 1), date(2027, 4, 1))
print(ctx.get_at(revenue, q))
print(ctx.get_at(cogs, q))
print(ctx.get_at(gross_profit, q))
print(ctx.get_at(rd, q))
print(ctx.get_at(sga, q))
print(ctx.get_at(income, q))
# print(ctx.dependencies(gross_profit, q))
