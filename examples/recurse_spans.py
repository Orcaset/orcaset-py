# Build a recursive revenue growth series keyed by Period.
#
# revenue[p] = revenue[prior p] * 1.1, expressed as an unfold: the prior cell
# is carried in generator state, so each period's cell references the previous
# period's cell object directly. Cross-series consumers address cells by
# ``revenue.at(period)``.

from collections.abc import Iterator
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import Context, F, Period, Series, print_deps


def revenue_cells() -> Iterator[tuple[Period, F[float]]]:
    cell: F[float] = F.pure(100.0, label="Initial revenue")
    for period in Period.seq(date(2025, 12, 31), relativedelta(years=1)):
        yield period, cell
        cell = cell.map(lambda value: value * 1.1, label="Revenue growth at 10%")


revenue = Series.from_cells(revenue_cells, label="Revenue")


ctx = Context()

third_period = Period(date(2027, 12, 31), date(2028, 12, 31))
third_value = revenue.at(third_period)

print(f"{third_period}: {third_value.run(ctx)}")
print("\n\n")
print_deps(ctx, third_value)
