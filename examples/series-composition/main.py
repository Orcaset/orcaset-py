# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Series composition with arithmetic combinators and nested Totals."""

from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Context,
    Maybe,
    Period,
    Series,
    Step,
    Stmt,
    Thunk,
    Total,
    accrual,
    fixed_width_table,
    get_at,
    isna,
    map_some,
    ops,
    period_union,
)

MONTHLY = relativedelta(months=1)
QUERY = accrual(YF.cmonthly)


@Series.define("revenue", QUERY, seed=next(Period.seq(date(2026, 1, 1), MONTHLY)))
def revenue_step(period: Period) -> tuple[Period, float | Thunk[float], Period]:
    """Each cell is the prior period's answer grown by 1%; seed is 100."""

    def value() -> Step[float]:
        prior = yield from get_at(revenue_step, period.from_start(-MONTHLY))
        return prior * 1.01 if not isna(prior) else 100.0

    return period, Thunk(value), period.from_end(MONTHLY)


revenue: Series[Period, Maybe[float], Maybe[float]] = revenue_step
cogs = ops.map_values("cogs", revenue, fn=map_some(lambda value: value * -0.5))
gross_profit = ops.add("gross_profit", revenue, cogs, merge_keys=period_union)


def constant_series(name: str, value: float) -> Series[Period, Maybe[float], Maybe[float]]:
    return Series.unfold(
        name,
        QUERY,
        seed=next(Period.seq(date(2026, 1, 1), MONTHLY)),
        step=lambda period: (period, value, period.from_end(MONTHLY)),
    )


rd = constant_series("r&d", -10.0)
sga = constant_series("sga", -10.0)
income = ops.add("income", gross_profit, rd, sga, merge_keys=period_union)

ctx = Context()
q = Period(date(2027, 3, 1), date(2027, 5, 15))

print("\nQuery line items over arbitrary periods:")
print(f"  Revenue @ {q}: \t{ctx.get_at(revenue, q):>10.2f}")
print(f"  COGS @ {q}: \t{ctx.get_at(cogs, q):>10.2f}")
print(f"{'-' * 58}\nGross profit @ {q}: \t{ctx.get_at(gross_profit, q):>10.2f}")

quarters = Period.list(date(2026, 1, 1), relativedelta(months=3), date(2027, 1, 1))
quarterly_statement = Stmt(
    Total(income, [Total(gross_profit, [revenue, cogs]), rd, sga])
).values_for_periods(ctx, quarters)

print("\nQuarterly statement")
print(fixed_width_table(quarterly_statement))
