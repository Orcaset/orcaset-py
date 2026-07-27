# Extend quarterly historicals by referencing the year-ago quarter.
#
# revenue[q] = revenue[q - 1 year] * 1.1
#
# The series queries its own cells by window: ``revenue.query(period.shift(years=-1))``.
# Query nodes are memoized per (series, query), so the lookback chain stays
# linear and shared. Window references also survive re-keying: the same
# year-ago query is correct whether the underlying cells are monthly or
# quarterly.
#
# ``query`` is total, so it answers ``Maybe[float]`` — a value or MISSING.
# Every consumer states a policy: ``unwrap`` asserts an answer must exist
# (which is how a recursive cell declares its base case is already covered),
# ``or_else`` supplies a default.
#
# ``query`` aggregates over arbitrary windows, prorating partial quarters by
# day count — windows may span many, one, part of one, or no underlying
# periods. Rebucketing to a coarser calendar is ``query`` mapped over that
# calendar, or ``resample`` to make the coarser calendar a series in its own
# right. ``select`` is the audit view: the clipped (key, cell) pairs behind a
# query's value.

from collections.abc import Iterator
from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    F,
    LeafSeries,
    Period,
    Pure,
    clip_daily,
    or_else,
    print_deps,
    resample,
    sum_cells,
    unwrap,
)

QUARTERLY = relativedelta(months=3)
YEARLY = relativedelta(years=1)
HISTORICALS = [100.0, 110.0, 120.0, 130.0]  # four quarters ending 2026-12-31


def revenue_cells() -> Iterator[tuple[Period, F[float]]]:
    quarters = iter(Period.seq(date(2025, 12, 31), QUARTERLY))
    for value, period in zip(HISTORICALS, quarters):
        yield period, Pure(value)
    for period in quarters:
        prior = revenue.query(period.shift(relativedelta(years=-1)))
        # The year-ago window is always covered — by historicals at first,
        # then by forecast cells — so an absent answer is a modelling error.
        yield period, prior.map(lambda a: unwrap(a) * 1.1, label=f"Revenue@{period} growth")


revenue = LeafSeries.from_cells(revenue_cells, clip_daily(), sum_cells(0.0), label="Revenue")


ctx = Context()

print("Quarterly revenue (historical + forecast):")
for period in islice(Period.seq(date(2025, 12, 31), QUARTERLY), 8):
    marker = "H" if period.end <= date(2026, 12, 31) else "F"
    print(f"  [{marker}] {period}: {unwrap(revenue.query(period).run(ctx)):8.2f}")

print("\nWindow queries:")
fy27 = revenue.query(Period(date(2026, 12, 31), date(2027, 12, 31)))
print(f"  FY2027 total:          {unwrap(fy27.run(ctx)):8.2f}")
straddle = Period(date(2026, 2, 15), date(2026, 5, 15))
value = unwrap(revenue.query(straddle).run(ctx))
print(f"  {straddle}: {value:8.2f}  (prorated across two quarters)")
inside = revenue.query(Period(date(2026, 1, 15), date(2026, 2, 14)))
print(f"  2026-01-15..2026-02-14: {unwrap(inside.run(ctx)):8.2f}  (part of one quarter)")
empty = revenue.query(Period(date(2020, 1, 1), date(2020, 12, 31)))
print(f"  2020 (no coverage):     {or_else(empty.run(ctx), 0.0):8.2f}  (a flow with no cells is 0)")

print("\nAudit view — select shows the clipped cells behind the straddling window:")
for key, cell in revenue.select(straddle).run(ctx):
    print(f"  {key}: {cell.run(ctx):8.2f}")

print("\nAnnual view (quarterly series rebucketed with query):")
for year in islice(Period.seq(date(2025, 12, 31), YEARLY), 3):
    print(f"  {year}: {unwrap(revenue.query(year).run(ctx)):8.2f}")

# Rebucketing as a series: `resample` tabulates the quarterly answers on an
# annual grid, producing a leaf whose cells are the source's query nodes. It
# has its own convention, so it can be queried, mapped and merged like any
# other line item — and its `select` shows the annual cells as evidence.
annual = resample(
    revenue,
    lambda: islice(Period.seq(date(2025, 12, 31), YEARLY), 3),
    lambda _, answer: or_else(answer, 0.0),
    clip_daily(),
    sum_cells(0.0),
    label="Revenue (annual)",
)

print("\nAnnual series (resampled onto a yearly grid):")
for key, cell in annual.items(ctx):
    print(f"  {key}: {unwrap(cell.run(ctx)):8.2f}")

print("\nDeps for the first forecast quarter:")
first_forecast = Period(date(2026, 12, 31), date(2027, 3, 31))
print_deps(ctx, revenue.query(first_forecast))
