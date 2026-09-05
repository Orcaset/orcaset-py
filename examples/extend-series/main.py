# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Compose series horizontally over a larger time domain."""

from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta

from orcaset import (
    YF,
    Cons,
    Context,
    Effect,
    Maybe,
    Na,
    Period,
    Series,
    Stmt,
    accrue,
    continue_series,
    covered,
    exact,
    fixed_width_table,
    get_at,
    multiply_some,
    period_split,
)

# ---- Inputs and assumptions ----
MONTH = relativedelta(months=1, day=31)  # Keep successive boundaries at month end.
Q3 = Period(date(2025, 6, 30), date(2025, 9, 30))
OCT = Q3.from_end(MONTH)
NOV = OCT.from_end(MONTH)
DEC = NOV.from_end(MONTH)
JAN = DEC.from_end(MONTH)
accrue_monthly = accrue(YF.cmonthly)

historical = [(Q3, 300.0)]
projected = [(Q3, 0.0), (OCT, 110.0), (NOV, Na), (DEC, 121.0)]


# ---- Series definitions ----
actuals = Series.of("Actuals", covered, historical)  # `covered` query function
projections = Series.of("Projections", accrue_monthly, projected)  # `accrue_monthly` query function


def terminal_revenue(
    last_node: Cons[Period, Maybe[float]] | None,
) -> Series[Period, Maybe[float], Maybe[float]]:
    """Grow revenue each month at a 2% annual rate after prior series ends."""
    # If there is no prior node (e.g., the prior series is empty), return an empty series.
    if last_node is None:
        return Series.of("Terminal growth", accrue_monthly, [])

    # Otherwise, grow revenue each month at a 2% annual rate after the prior series ends.
    # Note that this series is lazily bound to `revenue`
    @Series.define("Terminal growth", accrue_monthly, seed=last_node.key)
    def growth(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
        prior_month = yield from get_at(revenue, period)
        value = multiply_some((prior_month, (1 + 0.02 * YF.cmonthly(*period))))
        return period.from_end(MONTH), value, period.from_end(MONTH)

    return growth


# ---- Series composition ----
type Segment = Series[Period, Any, Maybe[float]]

components: Series[int, Segment, Maybe[Segment]] = Series.of(
    "Revenue components", exact, [(0, actuals), (1, projections)]
)
base: Series[Period, Maybe[float], Maybe[float]] = Series.flatten(
    "Actuals and projections",
    components.cells,
    query=covered,
    split_keys=period_split,
)

revenue = Series.flatten(
    "Revenue",
    continue_series("Revenue components", base, terminal_revenue),
    query=covered,
    split_keys=period_split,
)


# ---- Output ----
ctx = Context()
print(fixed_width_table(Stmt(revenue).values_for_periods(ctx, [Q3, OCT, NOV, DEC, JAN])))

partial_actual = Period(date(2025, 8, 31), Q3.end)
bad_crossing = Period(date(2025, 8, 31), NOV.end)
print(f"\nPartial actual ({partial_actual}):", ctx.get_at(revenue, partial_actual))
print(f"Bad seam crossing ({bad_crossing}):", ctx.get_at(revenue, bad_crossing))

print(f"\nBase Q3 value ({Q3}):", ctx.get_at(base, Q3))

half_forecast = Period(DEC.start, date(2026, 1, 15))
print(f"\nCross projection-forecast seam ({half_forecast}):", ctx.get_at(revenue, half_forecast))

print(f"\nDependencies for {JAN} revenue:\n{ctx.dependencies(revenue, JAN)}")
