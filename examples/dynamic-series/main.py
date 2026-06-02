from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from itertools import takewhile

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Period,
    Span,
    SpanSeriesDef,
    Stmt,
    Total,
    fixed_width_table,
    no_split,
    span,
    split_daily,
    sum_spans,
)

# --------------- ASSUMPTIONS ---------------
qtr_offset = relativedelta(months=3, day=31)
start_date = date(2025, 12, 31)
useful_life_qtrs = 4


# ------------------ CAPEX ------------------
@span.define(agg=sum_spans(0.0), label="Capital Expenditures")
def capex(_) -> Iterable[Span]:
    for period in Period.seq(start_date, qtr_offset):
        yield Span(period, Formula.pure(100.0), split_daily)


def create_cohort_series(cohort: Period) -> SpanSeriesDef:

    # Create the new series
    @span.define(agg=sum_spans(0.0), label=f"Qtr {cohort.end}")
    def depreciation_cohort(ctx: Context) -> Iterable[Span]:
        # Get total capex over the cohort period
        cohort_capex = capex.value(ctx, cohort)

        # Depreciate evenly over the next four calendar quarters
        depreciation = cohort_capex / useful_life_qtrs
        qtrs = Period.list(cohort.end, qtr_offset, cohort.end + qtr_offset * useful_life_qtrs)
        for qtr in qtrs:
            yield Span(qtr, depreciation, split_daily)

    return depreciation_cohort


# --------------- TEST SERIES FACTORY ---------------
cohort = create_cohort_series(Period(start_date, start_date + qtr_offset))

ctx = Context()
for period in Period.list(start_date, qtr_offset, date(2027, 6, 30)):
    print(f"{period}: {cohort.value(ctx, period).eval()}")

# Period(2025-12-31, 2026-03-31): 0.0
# Period(2026-03-31, 2026-06-30): 25.0
# Period(2026-06-30, 2026-09-30): 25.0
# Period(2026-09-30, 2026-12-31): 25.0
# Period(2026-12-31, 2027-03-31): 25.0
# Period(2027-03-31, 2027-06-30): 0.0


def cohort_keys(period: Period) -> Iterable[Period]:
    return takewhile(lambda c: c.start < period.end, Period.seq(start_date, qtr_offset))


depreciation_cohorts = span.keyed(
    keys=cohort_keys,
    series=create_cohort_series,
    label="Depreciation Cohorts",
)


@span.define(agg=sum_spans(0.0), label="Total Depreciation")
def total_depreciation(ctx: Context) -> Iterable[Span]:

    for period in Period.seq(start_date, qtr_offset):
        # Get the active cohorts for the period
        cohorts = depreciation_cohorts.items(ctx, period)
        # Query cohort values for the period
        cohort_values = [cohort.value(ctx, period) for _, cohort in cohorts]
        # Sum the cohort values
        total: Formula[float | None] = Formula.sequence(cohort_values).map(
            lambda v: sum(v or 0.0 for v in v)
        )
        # Yield the total
        yield Span(period, total, no_split)


# ------------- STRUCTURED OUTPUT -------------
ctx = Context()
stmt = Stmt(
    capex,
    Total(total_depreciation, [depreciation_cohorts]),
)

periods = Period.list(start_date, qtr_offset, date(2027, 12, 31))
results = stmt.values(ctx, periods)
print(fixed_width_table(results, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))

# Start                             2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30
# End                   2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30  2027-12-31
# Capital Expenditures                  100.00      100.00      100.00      100.00      100.00      100.00      100.00      100.00

#     Qtr 2026-03-31                      0.00       25.00       25.00       25.00       25.00        0.00        0.00        0.00
#     Qtr 2026-06-30                      0.00        0.00       25.00       25.00       25.00       25.00        0.00        0.00
#     Qtr 2026-09-30                      0.00        0.00        0.00       25.00       25.00       25.00       25.00        0.00
#     Qtr 2026-12-31                      0.00        0.00        0.00        0.00       25.00       25.00       25.00       25.00
#     Qtr 2027-03-31                      0.00        0.00        0.00        0.00        0.00       25.00       25.00       25.00
#     Qtr 2027-06-30                      0.00        0.00        0.00        0.00        0.00        0.00       25.00       25.00
#     Qtr 2027-09-30                      0.00        0.00        0.00        0.00        0.00        0.00        0.00       25.00
#     Qtr 2027-12-31                      0.00        0.00        0.00        0.00        0.00        0.00        0.00        0.00

# --------------------------------------------------------------------------------------------------------------------------------
# Total Depreciation                      0.00       25.00       50.00       75.00      100.00      100.00      100.00      100.00
