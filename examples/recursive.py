from collections.abc import Iterable, Iterator
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    CellFactory,
    Context,
    GridSeries,
    Period,
    Step,
    accrual,
    fetch,
    isna,
    map2_some,
    map_some,
)

MONTHLY = relativedelta(months=1)

by_days = accrual(lambda d1, d2: (d2 - d1).days)


def revenue_cells() -> Iterable[tuple[Period, float | CellFactory[float]]]:
    """Each cell is the prior period's answer grown by 1%; seed is 100."""

    def pairs() -> Iterator[tuple[Period, float | CellFactory[float]]]:
        periods = Period.seq(date(2026, 1, 1), MONTHLY)
        yield (next(periods), 100.0)

        for k in periods:

            def factory(p: Period = k) -> Step[float]:
                value = yield from fetch(revenue, p.from_start(-MONTHLY))
                if isna(value):
                    raise ValueError(f"missing prior for {p}")
                return value * 1.01

            yield k, factory

    return pairs()


revenue = GridSeries("revenue", revenue_cells, by_days)

cogs = revenue.map("cogs", map_some(lambda r: r * -0.5))

gross_profit = revenue.map2(
    "gross_profit",
    cogs,
    map2_some(lambda r, c: r + c),
    merge_keys=lambda domains: domains[0],
)

ctx = Context()
q = Period(date(2027, 3, 1), date(2027, 4, 1))
print(ctx.demand(revenue, q))
print(ctx.demand(cogs, q))
print(ctx.demand(gross_profit, q))
print(ctx.dependencies(gross_profit, q))
