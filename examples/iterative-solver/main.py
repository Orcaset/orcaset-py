# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Average-balance interest solved as a typed demand cycle."""

from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Effect,
    Maybe,
    Period,
    Series,
    accrue_or,
    add_some,
    get_at,
    isna,
    last,
    maybe_abs_distance,
)

# ---- Assumptions ----
START_DATE = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)
FIRST_MONTH = Period(START_DATE, START_DATE + MONTH)
MONTHLY_RATE = 0.10
OPENING_DEBT = 100.0

seed_date: date | None = None


@Series.define("Debt", last, seed=seed_date)
def debt(prior_date: date | None) -> Effect[tuple[date, Maybe[float], date]]:
    if prior_date is None:
        return START_DATE, OPENING_DEBT, START_DATE

    current_date = prior_date + MONTH
    begin = yield from get_at(debt, prior_date)
    interest_amt = yield from get_at(interest, Period(prior_date, current_date))

    return current_date, add_some((begin, interest_amt)), current_date


@Series.define("Interest", accrue_or(YF.act360, 0.0), seed=FIRST_MONTH)
def interest(period: Period) -> Effect[tuple[Period, float, Period]]:
    begin = yield from get_at(debt, period.start)

    # The ending period debt balance depends on the interest over the period.
    # Provide a seed and distance function so that the iterative solver has a starting point
    # and a way to check for convergence.
    end = yield from get_at(debt, period.end, seed=0.0, distance=maybe_abs_distance)

    if isna(begin):
        avg_balance = 0.0
    else:
        avg_balance = begin if isna(end) else (begin + end) * 0.5

    return period, avg_balance * MONTHLY_RATE, period.from_end(MONTH)


# ---- Output ----
if __name__ == "__main__":
    from itertools import islice

    from orcaset import Context, Stmt, fixed_width_table

    ctx = Context()
    periods = list(islice(Period.seq(START_DATE, MONTH), 4))
    print(fixed_width_table(Stmt(debt, interest).values_for_periods(ctx, periods)))
