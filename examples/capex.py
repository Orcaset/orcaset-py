# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Capex mapped to nested cohort depreciation schedules, then rolled up to totals."""

from collections.abc import Iterator
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    BaseSeries,
    CellFactory,
    Context,
    MapItemsSeries,
    Maybe,
    Period,
    Series,
    Step,
    accrual,
    exact,
    get,
    get_at,
    isna,
)

YEAR = relativedelta(years=1)
START = date(2025, 12, 31)

# Weight overlaps by actual calendar days (same as days / days).
by_days = accrual(lambda d1, d2: (d2 - d1).days)


# ---------- Capex ----------


def capex_cells() -> Iterator[tuple[Period, float]]:
    for period in Period.seq(START, YEAR):
        yield period, 100.0


capex = Series("capex", capex_cells, by_days)


# ---------- Cohort schedules ----------

type Cohort = Series[Period, Period, float, Maybe[float]]


def build_cohort(
    source_key: Period,
    source: BaseSeries[Period, Period, Maybe[float]],
) -> Cohort:
    """Depreciation schedule that re-fetches ``source`` at ``source_key`` when read."""

    def cells() -> Iterator[tuple[Period, CellFactory[float]]]:
        period = Period(source_key.end, source_key.end + YEAR)
        for _ in range(2):

            def factory(capex_period: Period = source_key) -> Step[float]:
                spend = yield from get_at(source, capex_period)
                if isna(spend):
                    raise ValueError(f"missing capex for {capex_period}")
                return spend / 2

            yield period, factory
            period = Period(period.end, period.end + YEAR)

    return Series(f"Depreciation@{source_key.end}", cells, exact)


def to_schedule(
    k: Period,
    source: BaseSeries[Period, Period, Maybe[float]],
) -> Cohort:
    return build_cohort(k, source)


cohort_schedules = MapItemsSeries(
    "cohort_schedules",
    capex,
    to_schedule,
    exact,
)


# ---------- Total depreciation ----------


def sum_cohorts_at_period(
    k: Period,
    source: BaseSeries[Period, Period, Maybe[Cohort]],
) -> Step[float]:
    """Annual total dep in ``k``: sum every eligible cohort's answer at ``k``."""
    total = 0.0
    keys = yield from get(source.keys())
    for spend_key in keys:
        if spend_key.end > k.end:
            break
        cohort = yield from get_at(source, spend_key)
        if isna(cohort):
            continue
        value = yield from get_at(cohort, k)
        if not isna(value):
            total += value
    return total


total_depreciation = MapItemsSeries(
    "total_depreciation",
    cohort_schedules,
    sum_cohorts_at_period,
    by_days,
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
    schedule = ctx.get_at(cohort_schedules, spend_key)
    if isna(schedule):
        raise RuntimeError(f"missing cohort for {spend_key}")
    cohort_rows.append((schedule.name, schedule))

print("Period end".ljust(22) + "".join(str(y.end).rjust(12) for y in years))
print("Capex".ljust(22) + "".join(f"{show(ctx.get_at(capex, y)):>12}" for y in years))
for name, schedule in cohort_rows:
    print(name.ljust(22) + "".join(f"{show(ctx.get_at(schedule, y)):>12}" for y in years))
print(
    "Total depreciation".ljust(22)
    + "".join(f"{show(ctx.get_at(total_depreciation, y)):>12}" for y in years)
)
print(f"\nCapex @ partial {partial}: {ctx.get_at(capex, partial)}")
print(f"Total dep @ partial {partial}: {ctx.get_at(total_depreciation, partial)}")

dep_year = years[1]
print(f"\nDeps: {cohort_rows[0][0]} @ {dep_year}\n")
print(ctx.dependencies(cohort_rows[0][1], dep_year))

print(f"\nDeps: total_depreciation @ {years[2]}\n")
print(ctx.dependencies(total_depreciation, years[2]))
