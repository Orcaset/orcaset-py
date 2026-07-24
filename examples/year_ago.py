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
# ``query`` aggregates over arbitrary windows, prorating partial quarters by
# day count — windows may span many, one, part of one, or no underlying
# periods. Rebucketing to a coarser calendar is just ``query`` mapped over
# that calendar. ``select`` is the audit view: the clipped (key, cell) pairs
# behind a query's value.

from collections.abc import Iterator
from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import Context, F, Period, Pure, flow, print_deps

QUARTERLY = relativedelta(months=3)
HISTORICALS = [100.0, 110.0, 120.0, 130.0]  # four quarters ending 2026-12-31


def revenue_cells() -> Iterator[tuple[Period, F[float]]]:
    quarters = iter(Period.seq(date(2025, 12, 31), QUARTERLY))
    for value, period in zip(HISTORICALS, quarters):
        yield period, Pure(value)
    for period in quarters:
        prior = revenue.query(period.shift(relativedelta(years=-1)))
        yield period, prior.map(lambda x: x * 1.1, label=f"Revenue@{period} growth")


revenue = flow(revenue_cells, label="Revenue")


ctx = Context()

print("Quarterly revenue (historical + forecast):")
for period in islice(Period.seq(date(2025, 12, 31), QUARTERLY), 8):
    marker = "H" if period.end <= date(2026, 12, 31) else "F"
    print(f"  [{marker}] {period}: {revenue.query(period).run(ctx):8.2f}")

print("\nWindow queries:")
fy27 = revenue.query(Period(date(2026, 12, 31), date(2027, 12, 31)))
print(f"  FY2027 total:          {fy27.run(ctx):8.2f}")
straddle = Period(date(2026, 2, 15), date(2026, 5, 15))
print(f"  {straddle}: {revenue.query(straddle).run(ctx):8.2f}  (prorated across two quarters)")
inside = revenue.query(Period(date(2026, 1, 15), date(2026, 2, 14)))
print(f"  2026-01-15..2026-02-14: {inside.run(ctx):8.2f}  (part of one quarter)")
empty = revenue.query(Period(date(2020, 1, 1), date(2020, 12, 31)))
print(f"  2020 (no coverage):     {empty.run(ctx):8.2f}")

print("\nAudit view — select shows the clipped cells behind the straddling window:")
for key, cell in revenue.select(straddle).run(ctx):
    print(f"  {key}: {cell.run(ctx):8.2f}")

print("\nAnnual view (quarterly series rebucketed with query):")
for year in islice(Period.seq(date(2025, 12, 31), relativedelta(years=1)), 3):
    print(f"  {year}: {revenue.query(year).run(ctx):8.2f}")

print("\nDeps for the first forecast quarter:")
first_forecast = Period(date(2026, 12, 31), date(2027, 3, 31))
print_deps(ctx, revenue.query(first_forecast))
