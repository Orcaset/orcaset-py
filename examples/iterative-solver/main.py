# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Average-balance interest solved as a typed demand cycle.

Interest depends on ending debt, and ending debt includes that interest
(payment-in-kind). The cyclic ``get_at`` of ending debt passes ``seed`` and
``distance`` typed against the fetched value — here ``float``, because
``exact_or(0.0)`` answers ``float`` rather than ``Maybe[float]``. That
spec is the cycle's cut: it is enough from any query entrypoint, so debt's
demand of interest does not need a spec.

A wrong seed type (for example ``seed="0"`` passing a ``str``) is a static
error against the ``get_at`` return type. Custom value types follow the same
pattern: provide a ``seed`` of that type and a ``distance`` that maps two of
them to a residual.
"""

from collections.abc import Iterator
from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import (
    CellFactory,
    Context,
    DateSeries,
    Period,
    PeriodSeries,
    Step,
    abs_distance,
    exact_or,
    get_at,
)

MODEL_START = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)
RATE = 0.10
always = exact_or(0.0)


@DateSeries.define("Debt", always)
def debt() -> Iterator[tuple[date, float | CellFactory[float]]]:
    yield MODEL_START, 100.0
    for p in Period.seq(MODEL_START, MONTH):

        def factory(period: Period = p) -> Step[float]:
            # No seed or distance function passed in either `get_at` here
            begin = yield from get_at(debt, period.start)
            interest_amt = yield from get_at(interest, period)
            return begin + interest_amt

        yield p.end, factory


@PeriodSeries.define("Interest", always)
def interest() -> Iterator[tuple[Period, CellFactory[float]]]:
    for p in Period.seq(MODEL_START, MONTH):

        def factory(period: Period = p) -> Step[float]:
            # Seed and distance function passed to the ending debt query here
            # The solver will use this single cut to break the cycle and find a solution
            begin = yield from get_at(debt, period.start)
            end = yield from get_at(debt, period.end, seed=0.0, distance=abs_distance)
            return RATE * 0.5 * (begin + end)

        yield p, factory


if __name__ == "__main__":
    ctx = Context()
    periods = list(islice(Period.seq(MODEL_START, MONTH), 4))
    dates = [MODEL_START, *(p.end for p in periods)]

    print("Date".ljust(16) + "".join(str(d).rjust(12) for d in dates))
    print("Debt".ljust(16) + "".join(f"{ctx.get_at(debt, d):12.2f}" for d in dates))
    print(
        "Interest".ljust(16)
        + "—".rjust(12)
        + "".join(f"{ctx.get_at(interest, p):12.2f}" for p in periods)
    )
