# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Capex mapped to nested cohort depreciation schedules, then rolled up."""

from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Cells,
    Context,
    Maybe,
    Period,
    Series,
    Step,
    Thunk,
    accrual,
    exact,
    get,
    get_at,
    isna,
)

YEAR = relativedelta(years=1)
START = date(2025, 12, 31)
by_days = accrual(lambda start, end: (end - start).days)

capex: Series[Period, float, Maybe[float]] = Series.unfold(
    "capex",
    by_days,
    seed=next(Period.seq(START, YEAR)),
    step=lambda period: (period, 100.0, period.from_end(YEAR)),
)

type Cohort = Series[Period, float, Maybe[float]]


def build_cohort(source_key: Period) -> Cohort:
    """A two-year schedule that re-fetches capex when a cell is read."""

    periods = list(Period.seq(source_key.end, YEAR, source_key.end + YEAR * 2))

    def depreciation() -> Step[float]:
        spend = yield from get_at(capex, source_key)
        if isna(spend):
            raise ValueError(f"missing capex for {source_key}")
        return spend / 2

    return Series.of(
        f"Depreciation@{source_key.end}",
        exact,
        [(period, Thunk(depreciation)) for period in periods],
    )


def cohort_step(
    cells: Cells[Period, float],
) -> Step[tuple[Period, Cohort, Cells[Period, float]] | None]:
    node = yield from get(cells)
    if node is None:
        return None
    return node.key, build_cohort(node.key), node.tail


cohort_schedules: Series[Period, Cohort, Maybe[Cohort]] = Series.unfold(
    "cohort_schedules",
    exact,
    seed=capex.cells,
    step=cohort_step,
)


def sum_cohorts_at_period(period: Period) -> Step[float]:
    total = 0.0
    node = yield from get(cohort_schedules.cells)
    while node is not None:
        if period < node.key:
            break
        cohort = yield from get(node.cell)
        value = yield from get_at(cohort, period)
        if not isna(value):
            total += value
        node = yield from get(node.tail)
    return total


def total_step(
    cells: Cells[Period, Cohort],
) -> Step[tuple[Period, Thunk[float], Cells[Period, Cohort]] | None]:
    node = yield from get(cells)
    if node is None:
        return None
    return node.key, Thunk(lambda: sum_cohorts_at_period(node.key)), node.tail


total_depreciation: Series[Period, float, Maybe[float]] = Series.unfold(
    "total_depreciation",
    by_days,
    seed=cohort_schedules.cells,
    step=total_step,
)

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

print("Period end".ljust(22) + "".join(str(year.end).rjust(12) for year in years))
print("Capex".ljust(22) + "".join(f"{show(ctx.get_at(capex, year)):>12}" for year in years))
for name, schedule in cohort_rows:
    print(name.ljust(22) + "".join(f"{show(ctx.get_at(schedule, year)):>12}" for year in years))
print(
    "Total depreciation".ljust(22)
    + "".join(f"{show(ctx.get_at(total_depreciation, year)):>12}" for year in years)
)
print(f"\nCapex @ partial {partial}: {ctx.get_at(capex, partial)}")
print(f"Total dep @ partial {partial}: {ctx.get_at(total_depreciation, partial)}")

dep_year = years[1]
print(f"\nDeps: {cohort_rows[0][0]} @ {dep_year}\n")
print(ctx.dependencies(cohort_rows[0][1], dep_year))

print(f"\nDeps: total_depreciation @ {years[2]}\n")
print(ctx.dependencies(total_depreciation, years[2]))
