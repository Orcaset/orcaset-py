# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Typed currency units prevent invalid cross-currency arithmetic."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Maybe,
    Period,
    Series,
    Step,
    Thunk,
    exact,
    get_at,
    map2_some,
    merge_cells,
    period_union,
)

MODEL_START = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)


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


def constant_series[V](name: str, value: V) -> Series[Period, V, Maybe[V]]:
    return Series.unfold(
        name,
        exact,
        seed=next(Period.seq(MODEL_START, MONTH)),
        step=lambda period: (period, value, period.from_end(MONTH)),
    )


def map2_series[A, B, C](
    name: str,
    left: Series[Period, A, Maybe[A]],
    right: Series[Period, B, Maybe[B]],
    fn: Callable[[Maybe[A], Maybe[B]], Maybe[C]],
) -> Series[Period, Maybe[C], Maybe[C]]:
    def value_at(period: Period) -> Step[Maybe[C]]:
        a = yield from get_at(left, period)
        b = yield from get_at(right, period)
        return fn(a, b)

    cells = merge_cells(
        name,
        [left.cells, right.cells],
        period_union,
        lambda period: Thunk(lambda: value_at(period)),
    )
    return Series(name, cells, lambda period, _cells: value_at(period))


usd_revenue = constant_series("USD revenue", USD(100.0))
eur_revenue = constant_series("EUR revenue", EUR(80.0))

# A type checker rejects the incompatible second operand passed to USD.__add__.
invalid_total = map2_series(
    "invalid total", usd_revenue, eur_revenue, map2_some(lambda a, b: a + b)
)

if __name__ == "__main__":
    ctx = Context()
    january = next(Period.seq(MODEL_START, MONTH))
    print(f"{usd_revenue.name}: {ctx.get_at(usd_revenue, january)}")
    print(f"{eur_revenue.name}: {ctx.get_at(eur_revenue, january)}")
    print(f"{invalid_total.name}: {ctx.get_at(invalid_total, january)}")
