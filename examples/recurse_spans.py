# Build a recursive revenue growth series keyed by Period.
#
# revenue[p] = revenue[prior p] * 1.1, expressed as a window query: each
# period's cell queries the series being defined over the prior period.
# Dependencies are stated as time windows, not stream positions, so re-keying
# the model (say yearly to quarterly) cannot silently misalign references.

from collections.abc import Iterator
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import Context, F, Period, flow, print_deps

YEARLY = relativedelta(years=1)


def revenue_cells() -> Iterator[tuple[Period, F[float]]]:
    periods = iter(Period.seq(date(2025, 12, 31), YEARLY))
    yield next(periods), F.pure(100.0, label="Initial revenue")
    for period in periods:
        prior = revenue.query(period.shift(-YEARLY))
        yield period, prior.map(lambda value: value * 1.1, label=f"Revenue@{period} growth")


revenue = flow(revenue_cells, label="Revenue")


ctx = Context()

third_period = Period(date(2027, 12, 31), date(2028, 12, 31))
third_value = revenue.query(third_period)

print(f"{third_period}: {third_value.run(ctx)}")
print("\n\n")
print_deps(ctx, third_value)
