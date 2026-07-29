from collections.abc import Generator, Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import Context, GridSeries, Maybe, Na, Period, Step, fetch, isna

MONTHLY = relativedelta(months=1)


def point(q: Period, cells: Iterable[tuple[Period, Step[float] | float]]) -> Step[Maybe[float]]:
    """Overlap ``q`` with cells; scale each by overlap days / cell days.

    Exact-key hits force the cell ``Step`` (base case). Partial / multi-cell
    queries ``fetch`` the full cell answer so values stay memoized.
    """
    total = 0.0
    hit = False
    for k, cell in cells:
        if k < q:
            continue
        if q < k:
            break
        if k == q:
            value = (yield from cell) if isinstance(cell, Generator) else cell
            return value
        value = yield from fetch(revenue, k)
        if isna(value):
            continue
        overlap_days = (min(k.end, q.end) - max(k.start, q.start)).days
        cell_days = (k.end - k.start).days
        total += value * (overlap_days / cell_days)
        hit = True
    return total if hit else Na


def revenue_cells() -> Iterable[tuple[Period, Step[float] | float]]:
    """Each cell is the prior period's answer grown by 1%; seed is 100."""
    periods = Period.seq(date(2026, 1, 1), MONTHLY)
    yield (next(periods), 100.0)

    for k in periods:

        def grow(p: Period = k) -> Step[float]:
            value = yield from fetch(revenue, p.from_start(-MONTHLY))
            if isna(value):
                raise ValueError(f"missing prior for {p}")
            return value * 1.01

        yield k, grow()


revenue = GridSeries("revenue", revenue_cells, point)

cogs = revenue.map("cogs", lambda r: Na if isna(r) else r * -0.5)

gross_profit = revenue.map2(
    "gross_profit",
    cogs,
    lambda r, c: Na if isna(r) or isna(c) else r + c,
    merge_keys=lambda domains: domains[0],  # cogs aliases revenue.keys()
)

ctx = Context()
q = Period(date(2027, 3, 1), date(2027, 4, 1))
print(ctx.demand(revenue, q))
print(ctx.demand(cogs, q))
print(ctx.demand(gross_profit, q))
print(ctx.dependencies(gross_profit, q))
