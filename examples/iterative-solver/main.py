# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Average-balance interest solved as a typed demand cycle."""

from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import (
    Cells,
    Context,
    Key,
    Period,
    Series,
    Step,
    Thunk,
    abs_distance,
    exact,
    get_at,
    value_or,
)

MODEL_START = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)
RATE = 0.10


def exact_or_zero[K: Key](q: K, cells: Cells[K, float]) -> Step[float]:
    return value_or((yield from exact(q, cells)), 0.0)


def debt_step(day: date) -> tuple[date, float | Thunk[float], date]:
    if day == MODEL_START:
        return day, 100.0, day + MONTH
    period = Period(day - MONTH, day)

    def value() -> Step[float]:
        begin = yield from get_at(debt, period.start)
        interest_amt = yield from get_at(interest, period)
        return begin + interest_amt

    return day, Thunk(value), day + MONTH


debt = Series.unfold("Debt", exact_or_zero, seed=MODEL_START, step=debt_step)


@Series.define("Interest", exact_or_zero, seed=next(Period.seq(MODEL_START, MONTH)))
def interest_step(period: Period) -> tuple[Period, Thunk[float], Period]:
    def value() -> Step[float]:
        begin = yield from get_at(debt, period.start)
        end = yield from get_at(debt, period.end, seed=0.0, distance=abs_distance)
        return RATE * 0.5 * (begin + end)

    return period, Thunk(value), period.from_end(MONTH)


interest = interest_step

if __name__ == "__main__":
    ctx = Context()
    periods = list(islice(Period.seq(MODEL_START, MONTH), 4))
    dates = [MODEL_START, *(period.end for period in periods)]

    print("Date".ljust(16) + "".join(str(day).rjust(12) for day in dates))
    print("Debt".ljust(16) + "".join(f"{ctx.get_at(debt, day):12.2f}" for day in dates))
    print(
        "Interest".ljust(16)
        + "—".rjust(12)
        + "".join(f"{ctx.get_at(interest, period):12.2f}" for period in periods)
    )
