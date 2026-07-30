"""Capex → cohort schedules → total depreciation."""

from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    CellFactory,
    Context,
    GridSeries,
    MapItemsSeries,
    Maybe,
    Na,
    Period,
    Rule,
    Series,
    Step,
    fetch,
    isna,
)

YEAR = relativedelta(years=1)
START = date(2025, 12, 31)


def accrual(q: Period, cells: Iterable[tuple[Period, Rule[None, float]]]) -> Step[Maybe[float]]:
    """Day-weighted accrual over memoized cell rules."""
    total = 0.0
    hit = False
    for k, cell in cells:
        if k < q:
            continue
        if q < k:
            break
        value = yield from fetch(cell, None)
        if k == q:
            return value
        overlap_days = (min(k.end, q.end) - max(k.start, q.start)).days
        cell_days = (k.end - k.start).days
        total += value * (overlap_days / cell_days)
        hit = True
    return total if hit else Na


def exact(q: Period, cells: Iterable[tuple[Period, Rule[None, float]]]) -> Step[Maybe[float]]:
    for k, cell in cells:
        if k < q:
            continue
        if q < k:
            break
        if k == q:
            return (yield from fetch(cell, None))
    return Na


# ---------- Capex ----------


def capex_cells() -> Iterable[tuple[Period, float]]:
    for period in Period.seq(START, YEAR):
        yield period, 100.0


capex = GridSeries("capex", capex_cells, accrual)


# ---------- Cohort schedules ----------

type Cohort = GridSeries[Period, Period, float, Maybe[float]]


def exact_cohort(
    q: Period, cells: Iterable[tuple[Period, Rule[None, Cohort]]]
) -> Step[Maybe[Cohort]]:
    for k, cell in cells:
        if k < q:
            continue
        if q < k:
            break
        if k == q:
            return (yield from fetch(cell, None))
    return Na


def build_cohort(
    source_key: Period,
    source: Series[Period, Period, Maybe[float]],
) -> Cohort:
    """Depreciation schedule that re-fetches ``source`` at ``source_key`` when read."""

    def cells() -> Iterable[tuple[Period, CellFactory[float]]]:
        period = Period(source_key.end, source_key.end + YEAR)
        for _ in range(2):

            def factory(capex_period: Period = source_key) -> Step[float]:
                spend = yield from fetch(source, capex_period)
                if isna(spend):
                    raise ValueError(f"missing capex for {capex_period}")
                return spend / 2

            yield period, factory
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


# ---------- Total depreciation ----------


def sum_cohorts_at_period(
    k: Period,
    source: Series[Period, Period, Maybe[Cohort]],
) -> Step[float]:
    """Annual total dep in ``k``: sum every eligible cohort's answer at ``k``."""
    total = 0.0
    keys = yield from fetch(source.keys(), None)
    for spend_key in keys:
        if spend_key.end > k.end:
            break
        cohort = yield from fetch(source, spend_key)
        if isna(cohort):
            continue
        value = yield from fetch(cohort, k)
        if not isna(value):
            total += value
    return total


total_depreciation = MapItemsSeries(
    "total_depreciation",
    cohort_schedules,
    sum_cohorts_at_period,
    accrual,
)


# ---------- Demo ----------

ctx = Context()
years = [
    Period(date(2025, 12, 31), date(2026, 12, 31)),
    Period(date(2026, 12, 31), date(2027, 12, 31)),
    Period(date(2027, 12, 31), date(2028, 12, 31)),
    Period(date(2028, 12, 31), date(2029, 12, 31)),
]
partial = Period(date(2025, 12, 31), date(2027, 6, 30))


def show(value: Maybe[float] | float) -> str:
    return "0.0" if isna(value) else f"{value}"


cohort_rows: list[tuple[str, Cohort]] = []
for spend_key in years[:3]:
    schedule = ctx.demand(cohort_schedules, spend_key)
    if isna(schedule):
        raise RuntimeError(f"missing cohort for {spend_key}")
    cohort_rows.append((schedule.name, schedule))

print("Period end".ljust(22) + "".join(str(y.end).rjust(12) for y in years))
print("Capex".ljust(22) + "".join(f"{show(ctx.demand(capex, y)):>12}" for y in years))
for name, schedule in cohort_rows:
    print(name.ljust(22) + "".join(f"{show(ctx.demand(schedule, y)):>12}" for y in years))
print(
    "Total depreciation".ljust(22)
    + "".join(f"{show(ctx.demand(total_depreciation, y)):>12}" for y in years)
)
print(f"\nCapex @ partial {partial}: {ctx.demand(capex, partial)}")
print(f"Total dep @ partial {partial}: {ctx.demand(total_depreciation, partial)}")

dep_year = years[1]
print(f"\nDeps: {cohort_rows[0][0]} @ {dep_year}\n")
print(ctx.dependencies(cohort_rows[0][1], dep_year))

print(f"\nDeps: total_depreciation @ {years[2]}\n")
print(ctx.dependencies(total_depreciation, years[2]))
