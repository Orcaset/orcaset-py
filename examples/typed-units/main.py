# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Typed currency units prevent invalid cross-currency arithmetic.

Series ``+`` is limited to ``Maybe[float]``, but the same protection applies
with ``map2``: a combiner typed for ``USD`` rejects an ``EUR`` operand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import repeat

from dateutil.relativedelta import relativedelta

from orcaset import Context, Period, PeriodSeries, exact, map2_some

MODEL_START = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)


# Define currency types to use as values
@dataclass(frozen=True, slots=True)
class USD:
    amount: float

    def __add__(self, other: USD) -> USD:
        if not isinstance(other, USD):
            return NotImplemented
        return USD(self.amount + other.amount)


@dataclass(frozen=True, slots=True)
class EUR:
    amount: float

    def __add__(self, other: EUR) -> EUR:
        if not isinstance(other, EUR):
            return NotImplemented
        return EUR(self.amount + other.amount)


# Define revenue series with currencies as values
usd_revenue = PeriodSeries(
    "USD revenue",
    lambda: zip(Period.seq(MODEL_START, MONTH), repeat(USD(100.0))),
    exact,
)
eur_revenue = PeriodSeries(
    "EUR revenue",
    lambda: zip(Period.seq(MODEL_START, MONTH), repeat(EUR(80.0))),
    exact,
)

# Cross-currency sum is rejected by the type checker:
# ``USD.__add__`` requires ``USD``, and ``eur_revenue`` is ``EUR``.
invalid_total = usd_revenue.map2("invalid total", eur_revenue, map2_some(lambda a, b: a + b))


if __name__ == "__main__":
    ctx = Context()
    january = next(Period.seq(MODEL_START, MONTH))
    print(f"{usd_revenue.name}: {ctx.get_at(usd_revenue, january)}")
    print(f"{eur_revenue.name}: {ctx.get_at(eur_revenue, january)}")

    # This line will raise a TypeError: unsupported operand type(s) for +: 'USD' and 'EUR'
    print(f"{invalid_total.name}: {ctx.get_at(invalid_total, january)}")
