# Custom values: units, citations, and metadata

Orcaset values can be custom types. Use custom types when invalid operations must be rejected (for example, enforcing unit boundaries) and when a number needs attached metadata (like source citations). Orcaset rules and series are type safe, so static type checkers can enforce value boundaries.

## Units that enforce valid combinations

Helpful for strongly enforcing values with units such as currencies. Type use if instructed by the user, otherwise us regular untyped numeric values.

Define immutable value types with narrowly typed operators. The annotation enables static checking and the runtime guard rejects incompatible operands when the operator is evaluated. Define all arithmetic dunders (e.g. `__sub__`, `__mul__`, `__neg__`, etc.).

```py
from dataclasses import dataclass


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
```

These types permit `USD + USD` and `EUR + EUR`. For `USD + EUR`, Python raises `TypeError` once neither operand supports the operation.

Compose series with custom values using the `ops.map`, `ops.map2`, or `ops.mapn` combinators.

```py
import operator
from datetime import date

from orcaset import Context, Maybe, Period, Series, maybe, ops, period_union, query

january = Period(date(2025, 12, 31), date(2026, 1, 31))
usd_product: Series[Period, USD, Maybe[USD]] = Series.of(
    "USD product revenue", query.exact, pairs=[(january, USD(100.0))]
)
usd_services: Series[Period, USD, Maybe[USD]] = Series.of(
    "USD services revenue", query.exact, pairs=[(january, USD(25.0))]
)
eur_revenue: Series[Period, EUR, Maybe[EUR]] = Series.of(
    "EUR revenue", query.exact, pairs=[(january, EUR(80.0))]
)

usd_total = ops.map2(
    "USD total",
    usd_product,
    usd_services,
    fn=maybe.map2_some(operator.add),
    merge_keys=period_union,
)

if __name__ == "__main__":
    ctx = Context()
    assert ctx.get_at(usd_total, january) == USD(125.0)
```

Replacing `usd_services` with `eur_revenue` produces a static error at the combining function in pyrefly. Keep concrete types through the series and callback instead of silencing errors with casts, `Any`, or ignores.

Only implement operations with defined domain semantics. For example, scaling money by a dimensionless factor may return the same currency, whereas FX conversion should explicitly consume a rate and return the target currency. Extracting `.amount` on both operands before adding bypasses unit enforcement.

Use queries compatible with the custom type. `query.exact` and `query.last` preserve arbitrary values; `query.accrue`, `query.avg`, and the convenience arithmetic combinators such as `ops.add` and `ops.scale` are typed for float-based values. A money wrapper needs a custom query for aggregation or proration, including explicit rules for units and missing values; adding `__add__` alone does not make it compatible with float-specific helpers.

## Citations attached to numeric inputs

Use a small citation record and a `float` subclass when sourced actuals (or other metadata) should remain usable by float-based model code. Initialize the immutable numeric payload in `__new__`, then attach the citation.

```py
from typing import Self


@dataclass(frozen=True, slots=True)
class Citation:
    source: str
    locator: str


class CitedFloat(float):
    citation: Citation
    __slots__ = ("citation",)

    def __new__(cls, value: float, citation: Citation) -> Self:
        obj = super().__new__(cls, value)
        obj.citation = citation
        return obj

    def __str__(self) -> str:
        return f"{float(self)} {self.citation}"

    def __repr__(self) -> str:
        return f"CitedFloat({float(self)!r}, {self.citation!r})"

    def __format__(self, spec: str) -> str:
        return str(self) if spec == "" else format(float(self), spec)
```

Choose citation fields that identify the actual source and fact: a workbook/sheet/cell, a document/page, or the EDGAR example's `accn`, `frame`, and `url`. Populate them from the source when loading the number. The following uses an illustrative local-file citation and keeps the actual and its forecast in one series:

```py
from dateutil.relativedelta import relativedelta

from orcaset import Effect, Thunk, YF, get_at

month = relativedelta(months=1, day=31)
sourced_revenue = CitedFloat(
    100.0, Citation(source="inputs/revenue.csv", locator="2026-01, revenue")
)


@Series.define("Revenue", query.accrue(YF.cmonthly), seed=january)
def revenue(
    period: Period,
) -> Effect[tuple[Period, Maybe[float] | Thunk[Maybe[float]], Period]]:
    if period == january:
        value = sourced_revenue
    else:
        prior = yield from get_at(revenue, period.from_start(-month))
        value = maybe.mul_some(prior, 1.10)
    return period, value, period.from_end(month)


if __name__ == "__main__":
    ctx = Context()
    actual = ctx.get_at(revenue, january)
    if isinstance(actual, CitedFloat):
        print(actual.citation)
    february = january.from_end(month)
    print(ctx.get_at(revenue, february))
    print(ctx.dependencies(revenue, february))
```

For external loading, return `Thunk(lambda: load_actual(...))` as the seed cell value, with the loader returning `CitedFloat`. This defers I/O until the value is demanded, as in the citations example. The step annotation above permits both immediate and deferred values.

This pattern deliberately leaves inherited arithmetic unchanged: `CitedFloat * float` returns a plain `float`. The forecast therefore has no `.citation` attribute. Its lineage comes from `yield from get_at(...)`, which lets the evaluation context record the dependency on the cited input. See [verification.md](verification.md) for inspecting dependencies.

Query operations (e.g. `query.accrue`, `query.avg`) may also discard metadata.

Numeric formatting such as `f"{actual:,.0f}"` intentionally shows only the amount; the custom `repr` makes citations visible in dependency output.
