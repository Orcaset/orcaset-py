# Create a model with the following structure:
# Capex: input series of capital expenditures by period
# Amort cohorts: each capex cell amortizes straight-line over the following
#   two periods (one cohort series per capex period)
# Total amort: ordered merge of all cohort series, summing equal periods
#
# Output summary:
# Period end        2026-12-31  2027-12-31  2028-12-31  2029-12-31
# Capex                    100         200           0           0
# Amort cohort 1             0          50          50           0
# Amort cohort 2             0           0         100          100
# Total amort                0          50         150          100

from collections.abc import Callable, Iterator
from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import Context, F, Period, Series, clip_daily, flow, print_deps, total

timeline: list[Period] = list(islice(Period.seq(date(2025, 12, 31), relativedelta(years=1)), 4))


# CAPEX — model input
capex = Series.from_pairs(
    [(timeline[0], 100.0), (timeline[1], 200.0)],
    clip_daily(),
    total(0.0),
    label="Capex",
)


# AMORT COHORTS — one series per capex period, defined against the capex window
def amort_cells(source: Period, label: str) -> Callable[[], Iterator[tuple[Period, F[float]]]]:
    def cells() -> Iterator[tuple[Period, F[float]]]:
        expense = capex.query(source)
        period = Period(source.end, source.end + relativedelta(years=1))
        for _ in range(2):
            yield period, expense.map(lambda x: x / 2, label=f"{label}@{period}")
            period = Period(period.end, period.end + relativedelta(years=1))

    return cells


cohorts: list[Series[Period, float]] = [
    flow(amort_cells(period, f"Amort cohort {i}"), label=f"Amort cohort {i}")
    for i, period in enumerate(timeline[:2], start=1)
]


# TOTAL AMORT — merge cohort schedules, summing equal periods
total_amort = Series.merge(cohorts, lambda a, b: a + b, label="Total amort")


# OUTPUT
ctx = Context()

rows: list[tuple[str, Series[Period, float]]] = [
    ("Capex", capex),
    *((cohort.label, cohort) for cohort in cohorts),
    ("Total amort", total_amort),
]

print("Period end".ljust(16) + "".join(str(p.end).rjust(12) for p in timeline))
for name, series in rows:
    values = (series.query(period).run(ctx) for period in timeline)
    print(name.ljust(16) + "".join(f"{value:12.0f}" for value in values))

print(f"\n{'-' * 16}\nTotal amort deps for {timeline[2]}:\n")
print_deps(ctx, total_amort.query(timeline[2]))
