# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Average-balance interest solved as a typed demand cycle."""

from datetime import date
from itertools import islice

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Context,
    Effect,
    Period,
    Series,
    Thunk,
    abs_distance,
    accrual_or,
    get_at,
    last_or,
)

MODEL_START = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)
MONTHLY_RATE = 0.10


@Series.define("Debt", last_or(0.0), seed=MODEL_START)
def debt(day: date) -> tuple[date, float | Thunk[float], date]:
    if day == MODEL_START:
        return day, 100.0, day + MONTH
    period = Period(day - MONTH, day)

    def value() -> Effect[float]:
        begin = yield from get_at(debt, period.start)
        interest_amt = yield from get_at(interest, period)
        return begin + interest_amt

    return day, Thunk(value), day + MONTH


@Series.define(
    "Interest", accrual_or(YF.act360, 0.0), seed=Period(MODEL_START, MODEL_START + MONTH)
)
def interest(period: Period) -> tuple[Period, Thunk[float], Period]:
    def value() -> Effect[float]:
        begin = yield from get_at(debt, period.start)
        end = yield from get_at(debt, period.end, seed=0.0, distance=abs_distance)
        return (begin + end) * 0.5 * MONTHLY_RATE

    return period, Thunk(value), period.from_end(MONTH)


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
