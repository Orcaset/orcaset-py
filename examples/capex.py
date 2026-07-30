"""Capex → cohort schedules via a local MapItemsSeries prototype (not in the library yet)."""

from collections.abc import Callable, Generator, Hashable, Iterable, Iterator
from datetime import date
from typing import cast

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    GridSeries,
    Key,
    Maybe,
    Na,
    Period,
    QueryFn,
    Replayable,
    Rule,
    Series,
    Step,
    fetch,
    isna,
)
from orcaset.series import _as_step, _ascending_pairs

YEAR = relativedelta(years=1)
START = date(2025, 12, 31)


def accrual(q: Period, cells: Iterable[tuple[Period, Step[float] | float]]) -> Step[Maybe[float]]:
    """Overlap ``q`` with cells; scale each by overlap days / cell days."""
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
        value = (yield from cell) if isinstance(cell, Generator) else cell
        if isna(value):
            continue
        overlap_days = (min(k.end, q.end) - max(k.start, q.start)).days
        cell_days = (k.end - k.start).days
        total += value * (overlap_days / cell_days)
        hit = True
    return total if hit else Na


def exact(q: Period, cells: Iterable[tuple[Period, Step[float] | float]]) -> Step[Maybe[float]]:
    """Exact-key query; misses are ``Na``."""
    for k, cell in cells:
        if k < q:
            continue
        if q < k:
            break
        if k == q:
            if isinstance(cell, Generator):
                return (yield from cell)
            return cell
    return Na


# ---------- MapItemsSeries prototype (example-local) ----------


class _ItemCells[K: Key, W, V](Rule[None, Iterable[tuple[K, Step[V] | V]]]):
    """Cell stream: for each source key, ``fn(k, source)`` (fn may fetch)."""

    def __init__(
        self,
        name: str,
        source: Series[K, K, W],
        fn: Callable[[K, Series[K, K, W]], Step[V] | V],
    ) -> None:
        super().__init__(f"{name}.cells")
        self._source = source
        self._fn = fn

    def compute(self, key: None) -> Step[Iterable[tuple[K, Step[V] | V]]]:
        keys = yield from fetch(self._source.keys(), None)

        def pairs() -> Iterator[tuple[K, Step[V] | V]]:
            for k in keys:

                def cell(src: K = k) -> Step[V]:
                    return (yield from _as_step(self._fn(src, self._source)))

                yield k, cell()

        return Replayable(_ascending_pairs(pairs()))


class MapItemsSeries[Q: Hashable, K: Key, V, W, A](Series[Q, K, A]):
    """Map each source key via ``fn(k, source)``, then query the derived stream.

    ``source`` must be ``Series[K, K, W]`` so domain keys are valid point queries.
    ``fn`` receives the key and source series (not a resolved value) so it can
    ``fetch`` for dependency tracking. ``keys()`` aliases ``source.keys()``.
    """

    def __init__(
        self,
        name: str,
        source: Series[K, K, W],
        fn: Callable[[K, Series[K, K, W]], Step[V] | V],
        query: QueryFn[Q, K, V, A],
    ) -> None:
        super().__init__(name)
        self._source = source
        self._fn = fn
        self._query = query
        self._cells = cast(
            Rule[None, Iterable[tuple[K, Step[V] | V]]],
            _ItemCells(name, source, fn),
        )

    def keys(self) -> Rule[None, Iterable[K]]:
        return self._source.keys()

    def compute(self, q: Q, /) -> Step[A]:
        cells = yield from fetch(self._cells, None)
        return (yield from _as_step(self._query(q, cells)))


# ---------- Capex ----------


def capex_cells() -> Iterable[tuple[Period, float]]:
    for period in Period.seq(START, YEAR):
        yield period, 100.0


capex = GridSeries("capex", capex_cells, accrual)


# ---------- Cohort schedules via MapItemsSeries ----------

type Cohort = GridSeries[Period, Period, float, Maybe[float]]


def exact_cohort(
    q: Period,
    cells: Iterable[tuple[Period, Step[Cohort] | Cohort]],
) -> Step[Maybe[Cohort]]:
    for k, cell in cells:
        if k < q:
            continue
        if q < k:
            break
        if k == q:
            if isinstance(cell, Generator):
                return (yield from cell)
            return cell
    return Na


def build_cohort(
    source_key: Period,
    source: Series[Period, Period, Maybe[float]],
) -> Cohort:
    """Depreciation schedule that re-fetches ``source`` at ``source_key`` when read."""

    def cells() -> Iterable[tuple[Period, Step[float]]]:
        period = Period(source_key.end, source_key.end + YEAR)
        for _ in range(2):

            def half(capex_period: Period = source_key) -> Step[float]:
                spend = yield from fetch(source, capex_period)
                if isna(spend):
                    raise ValueError(f"missing capex for {capex_period}")
                return spend / 2

            yield period, half()
            period = Period(period.end, period.end + YEAR)

    return GridSeries(f"Depreciation@{source_key.end}", cells, exact)


def to_schedule(
    k: Period,
    source: Series[Period, Period, Maybe[float]],
) -> Cohort:
    return build_cohort(k, source)


cohort_schedules = MapItemsSeries(
    "cohort_schedules",
    capex,
    to_schedule,
    exact_cohort,
)


# ---------- Demo ----------

ctx = Context()
capex_q = Period(date(2025, 12, 31), date(2027, 6, 30))
first = Period(date(2025, 12, 31), date(2026, 12, 31))
dep_year = Period(date(2026, 12, 31), date(2027, 12, 31))

print(f"Capex @ {capex_q}: {ctx.demand(capex, capex_q)}")

schedule = ctx.demand(cohort_schedules, first)
print(f"cohort_schedules @ {first}: {schedule}")
assert not isna(schedule)
print(f"schedule @ {dep_year}: {ctx.demand(schedule, dep_year)}")

print(f"\nDeps: cohort_schedules @ {first}\n")
print(ctx.dependencies(cohort_schedules, first))

print(f"\nDeps: schedule @ {dep_year}\n")
print(ctx.dependencies(schedule, dep_year))
