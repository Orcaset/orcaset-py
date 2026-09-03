# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Series composition with arithmetic combinators."""

from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Context,
    Maybe,
    Period,
    Series,
    Stmt,
    Thunk,
    Total,
    accrue,
    fixed_width_table,
    get_at,
    isna,
    ops,
    period_union,
)

START = date(2026, 1, 1)
MONTHLY = relativedelta(months=1)
accrue_monthly = accrue(YF.cmonthly)


# ---- Model definition ----
@Series.define("Revenue", accrue_monthly, seed=Period(START, START + MONTHLY))
def revenue(period: Period) -> tuple[Period, Thunk[float], Period]:
    """Each cell is the prior period's answer grown by 1%; seed is 100."""

    def value():
        prior_value = yield from get_at(revenue, period.from_start(-MONTHLY))
        return prior_value * 1.01 if not isna(prior_value) else 100.0

    return period, Thunk(value), period.from_end(MONTHLY)


cogs = ops.scale("COGS", revenue, -0.5)
gross_profit = ops.add("Gross Profit", revenue, cogs, merge_keys=period_union)


def constant_series(name: str, value: float) -> Series[Period, Maybe[float], Maybe[float]]:
    """Helper function that returns a constant value at a regular interval."""
    return Series.unfold(
        name,
        accrue_monthly,
        seed=next(Period.seq(date(2026, 1, 1), MONTHLY)),
        step=lambda period: (period, value, period.from_end(MONTHLY)),
    )


rd = constant_series("R&D", -10.0)
sga = constant_series("SGA", -10.0)
income = ops.add("Income", gross_profit, rd, sga, merge_keys=period_union)


# ---- Output ----
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
