# Create a model with the following structure:
# Capex: input series of capital expenditures by period
# Amort cohorts: each capex cell amortizes straight-line over the following
#   two periods (one cohort series per capex period)
# Total amort: pointwise sum of all cohort series
#
# Cohorts cover disjoint spans, so every cohort is asked every period and
# answers MISSING outside its own. `or_else(a, 0.0)` states the policy: an
# absent cohort contributes its additive identity. That is the one thing a
# query-level combine needs which a stream-level merge got for free.
#
# Output summary:
# Period end        2026-12-31  2027-12-31  2028-12-31  2029-12-31
# Capex                    100         200           0           0
# Amort cohort 1             0          50          50           0
# Amort cohort 2             0           0         100         100
# Total amort                0          50         150         100

from collections.abc import Callable, Iterator
from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import (
    Cells,
    Context,
    F,
    LeafSeries,
    MapNSeries,
    Period,
    Series,
    clip_daily,
    or_else,
    print_deps,
    sum_cells,
    unwrap,
)

timeline: list[Period] = list(islice(Period.seq(date(2025, 12, 31), relativedelta(years=1)), 4))


# CAPEX — model input
capex = LeafSeries.from_pairs(
    [(timeline[0], 100.0), (timeline[1], 200.0)],
    clip_daily(),
    sum_cells(0.0),
    label="Capex",
)


# AMORT COHORTS — one series per capex period, defined against the capex window
def amort_cells(source: Period, label: str) -> Callable[[], Cells[Period, float]]:
    def cells() -> Iterator[tuple[Period, F[float]]]:
        # `capex` is a flow: an uncovered window answers 0.0, never MISSING.
        # `unwrap` records that expectation instead of silently defaulting.
        expense = capex.query(source)
        period = Period(source.end, source.end + relativedelta(years=1))
        for _ in range(2):
            yield period, expense.map(lambda a: unwrap(a) / 2, label=f"{label}@{period}")
            period = Period(period.end, period.end + relativedelta(years=1))

    return cells


cohorts: list[Series[Period, float]] = [
    LeafSeries.from_cells(
        amort_cells(period, f"Amort cohort {i}"),
        clip_daily(),
        sum_cells(0.0),
        label=f"Amort cohort {i}",
    )
    for i, period in enumerate(timeline[:2], start=1)
]


# TOTAL AMORT — pointwise sum of the cohort schedules
total_amort = MapNSeries(
    cohorts,
    lambda answers: sum(or_else(a, 0.0) for a in answers),
    label="Total amort",
)


# OUTPUT
ctx = Context()

rows: list[tuple[str, Series[Period, float]]] = [
    ("Capex", capex),
    *((cohort.label, cohort) for cohort in cohorts),
    ("Total amort", total_amort),
]

print("Period end".ljust(16) + "".join(str(p.end).rjust(12) for p in timeline))
for name, series in rows:
    values = (unwrap(series.query(period).run(ctx)) for period in timeline)
    print(name.ljust(16) + "".join(f"{value:12.0f}" for value in values))

print(f"\n{'-' * 16}\nTotal amort deps for {timeline[2]}:\n")
print_deps(ctx, total_amort.query(timeline[2]))
