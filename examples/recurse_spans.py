# Build a recursive revenue growth series keyed by Period.
#
# revenue[p] = revenue[prior p] * 1.1, expressed as a window query: each
# period's cell queries the series being defined over the prior period.
# Dependencies are stated as time windows, not stream positions, so re-keying
# the model (say yearly to quarterly) cannot silently misalign references.

from collections.abc import Iterator
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import Context, F, LeafSeries, Period, clip_daily, print_deps, sum_cells, unwrap

YEARLY = relativedelta(years=1)


def revenue_cells() -> Iterator[tuple[Period, F[float]]]:
    periods = iter(Period.seq(date(2025, 12, 31), YEARLY))
    yield next(periods), F.pure(100.0, label="Initial revenue")
    for period in periods:
        prior = revenue.query(period.shift(-YEARLY))
        yield period, prior.map(lambda a: unwrap(a) * 1.1, label=f"Revenue@{period} growth")


revenue = LeafSeries.from_cells(revenue_cells, clip_daily(), sum_cells(0.0), label="Revenue")


ctx = Context()

third_period = Period(date(2027, 12, 31), date(2028, 12, 31))
third_value = revenue.query(third_period)

print(f"{third_period}: {unwrap(third_value.run(ctx))}")
print("\n\n")
print_deps(ctx, third_value)
