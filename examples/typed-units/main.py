# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Typed currency units prevent invalid cross-currency arithmetic."""

import operator
from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Period,
    Series,
    exact,
    map2_some,
    ops,
    period_union,
)

MODEL_START = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)


# ---- Define currency types ----
# Each currency type can only be added with itself.
# This is both a static type checking and a compile-time guarantee.


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


# ---- Define constant value series ----
usd_product = Series.of(
    "USD product revenue", exact, pairs=zip(Period.seq(MODEL_START, MONTH), [USD(100.0)])
)
usd_services = Series.of(
    "USD services revenue", exact, pairs=zip(Period.seq(MODEL_START, MONTH), [USD(25.0)])
)
eur_revenue = Series.of(
    "EUR revenue", exact, pairs=zip(Period.seq(MODEL_START, MONTH), [EUR(80.0)])
)

# ---- Demonstrate type-aware composition ----

# OK: same-currency total composes.
usd_total = ops.map2(
    "USD total",
    usd_product,
    usd_services,
    fn=map2_some(operator.add),
    merge_keys=period_union,
)

# ERROR: different-currency total is rejected where the series are
# composed: pyrefly reports the ``fn`` argument as incompatible with the
# operands' value types, and evaluating it raises ``TypeError``.
invalid_total = ops.map2(
    "invalid total",
    usd_product,
    eur_revenue,
    fn=map2_some(operator.add),
    merge_keys=period_union,
)

if __name__ == "__main__":
    ctx = Context()
    january = Period(MODEL_START, MODEL_START + MONTH)
    print(f"{usd_product.name}: {ctx.get_at(usd_product, january)}")
    print(f"{usd_services.name}: {ctx.get_at(usd_services, january)}")
    print(f"{usd_total.name}: {ctx.get_at(usd_total, january)}")
    print(f"{eur_revenue.name}: {ctx.get_at(eur_revenue, january)}")

    try:
        print(f"{invalid_total.name}: {ctx.get_at(invalid_total, january)}")
    except TypeError:
        print("ERROR: Cannot add USD and EUR.")
