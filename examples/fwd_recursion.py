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
    print_deps,
    sum_cells,
    unwrap,
)

# Forward recursion variant
#  - Values for periods on or after 2027 are equal to 100.0
#  - Values for periods before 2027 are calculated by backsolving the next
# year's value and subtracting 1.0
YEARLY = relativedelta(years=1)


def target_cells() -> Iterator[tuple[Period, F[float]]]:
    for period in Period.seq(date(2023, 1, 1), YEARLY):
        if period.start.year >= 2027:
            yield period, Pure(100.0, label=f"Terminal@{period.start.year}")
        else:
            nxt = target.query(period.shift(YEARLY))  # forward self-reference
            yield period, nxt.map(lambda a: unwrap(a) - 1.0, label=f"Backsolve@{period.start.year}")


target = LeafSeries.from_cells(target_cells, clip_daily(), sum_cells(0.0), label="Target")

ctx = Context()
for period in islice(Period.seq(date(2023, 1, 1), YEARLY), 7):
    print(f"{period.start.year}: {unwrap(target.query(period).run(ctx))}")


print_deps(ctx, target.query(Period(date(2023, 1, 1), date(2027, 1, 1))))


# Partial period variant
#  - Starts with a seed value of 100.0 for 2027
#  - Values for subsequent years are calculated by multiplying the previous year's Q4 value by 4.0

YEARLY = relativedelta(years=1)
START = date(2027, 1, 1)


def quadrupled_q4_cells() -> Iterator[tuple[Period, F[float]]]:
    years = iter(Period.seq(START, YEARLY))
    yield next(years), Pure(100.0, label="CY2027 seed")
    for period in years:
        q4 = target.query(Period(period.start - relativedelta(months=3), period.start))
        yield period, q4.map(lambda a: unwrap(a) * 4.0, label=f"CY{period.start.year} = Q4 x 4")


target = LeafSeries.from_cells(quadrupled_q4_cells, clip_daily(), sum_cells(0.0), label="Target")

ctx = Context()
for period in islice(Period.seq(date(2027, 1, 1), YEARLY), 5):
    print(f"{period.start.year}: {unwrap(target.query(period).run(ctx))}")
