# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Point-in-time balance that compounds from period-domain interest."""

from collections.abc import Iterator
from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import (
    CellFactory,
    CellStream,
    Context,
    Period,
    Series,
    Step,
    accrual,
    exact,
    get,
    get_at,
    isna,
)

MONTHLY = relativedelta(months=1, day=31)
SEED = date(2019, 12, 31)
RATE = 0.05
by_days = accrual(lambda a, b: (b - a).days)


def interest_cells() -> Iterator[tuple[Period, CellFactory[float]]]:
    for p in Period.seq(SEED, MONTHLY):

        def factory(period: Period = p) -> Step[float]:
            bal = yield from get_at(balance, period.start)
            if isna(bal):
                return 0.0
            return bal * RATE

        yield p, factory


interest = Series("interest", interest_cells, by_days)


def balance_cells() -> CellStream[date, float]:
    periods = yield from get(interest.keys())

    yield SEED, 100.0
    for p in periods:

        def factory(period: Period = p) -> Step[float]:
            bal = yield from get_at(balance, period.start)
            interest_amt = yield from get_at(interest, period)
            if isna(bal) or isna(interest_amt):
                raise ValueError(f"missing inputs for balance at {period.end}")
            return bal + interest_amt

        yield p.end, factory


balance = Series("balance", balance_cells, exact)


ctx = Context()
periods = list(islice(Period.seq(SEED, MONTHLY), 4))
dates = [SEED, *(p.end for p in periods)]

print("Date".ljust(16) + "".join(str(d).rjust(12) for d in dates))
print("Balance".ljust(16) + "".join(f"{ctx.get_at(balance, d):12.2f}" for d in dates))
print(
    "Interest".ljust(16)
    + "—".rjust(12)
    + "".join(f"{ctx.get_at(interest, p):12.2f}" for p in periods)
)
