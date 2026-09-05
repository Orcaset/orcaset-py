# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Capex mapped to nested cohort depreciation schedules, then rolled up."""

from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Effect,
    Maybe,
    Period,
    Rule,
    Series,
    Stmt,
    Thunk,
    Total,
    accrue,
    exact,
    fixed_width_table,
    get,
    get_at,
    isna,
    map_cells,
    scan_cells,
)

# ---- Inputs and assumptions ----
YEAR = relativedelta(years=1)
START = date(2025, 12, 31)
by_days = accrue(lambda start, end: (end - start).days)

# ---- Series definitions ----
capex: Series[Period, float, Maybe[float]] = Series.unfold(
    "capex",
    by_days,
    seed=next(Period.seq(START, YEAR)),
    step=lambda period: (period, 100.0, period.from_end(YEAR)),
)

type Cohort = Series[Period, float, Maybe[float]]
type CohortRules = tuple[Rule[Cohort], ...]


def build_cohort(source_key: Period) -> Cohort:
    """Create a two-year depreciation schedule for a given capex period."""

    periods = list(Period.seq(source_key.end, YEAR, source_key.end + YEAR * 2))

    def depreciation() -> Effect[float]:
        spend = yield from get_at(capex, source_key)
        if isna(spend):
            raise ValueError(f"missing capex for {source_key}")
        return spend / 2

    return Series.of(
        f"Depreciation@{source_key.end}",
        by_days,
        [(period, Thunk(depreciation)) for period in periods],
    )


cohort_schedules: Series[Period, Cohort, Maybe[Cohort]] = Series(
    "cohort_schedules",
    map_cells(
        "cohort_schedules",
        capex.cells,
        lambda source_key, _cell: build_cohort(source_key),
    ),
    exact,
)


def sum_cohorts(cohorts: CohortRules, period: Period) -> Effect[float]:
    total = 0.0
    for cell in cohorts:
        cohort = yield from get(cell)
        value = yield from get_at(cohort, period)
        if not isna(value):
            total += value
    return total


def rollup(
    prior: CohortRules,
    period: Period,
    current: Rule[Cohort],
) -> tuple[Thunk[float], CohortRules]:
    """Carry cohort rules forward without evaluating their schedules."""
    cohorts = (*prior, current)
    return Thunk(lambda: sum_cohorts(cohorts, period)), cohorts


total_depreciation: Series[Period, float, Maybe[float]] = Series(
    "total_depreciation",
    scan_cells(
        "total_depreciation",
        cohort_schedules.cells,
        seed=(),
        fn=rollup,
    ),
    by_days,
)


# ---- Output ----
ctx = Context()
years = [
    Period(date(2025, 12, 31), date(2026, 12, 31)),
    Period(date(2026, 12, 31), date(2027, 12, 31)),
    Period(date(2027, 12, 31), date(2028, 12, 31)),
    Period(date(2028, 12, 31), date(2029, 12, 31)),
]
partial = Period(date(2025, 12, 31), date(2027, 6, 30))


cohorts: list[Cohort] = []
for spend_key in years[:3]:
    schedule = ctx.get_at(cohort_schedules, spend_key)
    if isna(schedule):
        raise RuntimeError(f"missing cohort for {spend_key}")
    cohorts.append(schedule)

statement = Stmt(capex, Total(total_depreciation, cohorts))
print(fixed_width_table(statement.values_for_periods(ctx, years)))
print(f"\nCapex @ partial {partial}: {ctx.get_at(capex, partial)}")
print(f"Total dep @ partial {partial}: {ctx.get_at(total_depreciation, partial)}")
print(f"First cohort @ partial {partial}: {ctx.get_at(cohorts[0], partial)}")
