# Core Orcaset Modeling Docs

## Layout and code patterns

Follow these rules when building or modifying Orcaset models.

- Organize code so that models and views/outputs are separated. Imports only used by outputs, context creation, query periods and dates, formatting, and printing/saving are all output code that should be separated from model code.
    - Small models (less than ~500 lines): Single file with all outputs behind an `if __name___...` clause.
    - Larger models (greater than ~500 lines): Separate file(s) for model component(s) and output(s). Model should be organized into logical components (e.g., income, balance sheet, schedules, etc). Separate distinct outputs into separate files (e.g., pro forma, sensitivity, etc). Use `if TYPECHECKING` clauses for circular type imports.
- All value and series definitions should be at the module/file level so that they can be imported from external scripts.
- ALWAYS AVOID helper and builder functions, even if there are many similarly constructed line items. Helpers make it harder to modify individual line items and obfuscate definitions.
- Lift values users may want to sensitize into rules with `Val`.
- NEVER use horizon or end dates in model definitions unless there is a specific financial reason (e.g., loan maturity date, sale date). Series are meant to be infinite; model-level horizons may artificially introduce out of bounds `Na` values on query.
- Type ignore comments and type casts are STRICTLY prohibited. `Any` types are ONLY permitted in cases where an exsistential type is required by the type checker. Any other use of `Any` types is strictly prohibited. Add explicity type annotations if required by the type checker.
- Do not create README or other extraneous files unless requested.
- Use `numpy-financial` if available for IRR, NPV, and similar financial functions.

## Dates and periods

Use `datetime.date` objects to represent dates and `orcaset.Period` for spans of dates.

```py
from collections.abc import Generator
from datetime import date
from dateutil.relativedelta import relativedelta
from orcaset import Period

start = date(2025, 12, 31)
end = date(2026, 3, 31)
q1_2026 = Period(start, end)
# get period from end of current period
q2_2026 = q1_2026.from_end(relativedelta(months=3, day=31))
# get period from start of current period
q4_2026 = q1_2026.from_start(relativedelta(months=-3, day=31))
# shift start and end date by one year
q1_2025 = q1_2026.shift(relativedelta(years=-1))
# generator of sequential periods
quarters_gen: Generator[Period] = Period.seq(start, relativedelta(months=3, day=31))
# list of sequential periods
quarters_list: list[Period] = Period.list(start, relativedelta(months=3, day=31), end)
```

ALWAYS define calendar periods as rolling on the last day of the month unless instructed otherwise.

Correct examples:
- Q1 2025: (2024-12-31, 2025-03-31)
- June 2027: (2027-05-31, 2027-06-30)
- 2000: (1999-12-31, 2000-12-31)

## Maybe

`Maybe[V]` is a union type of `V` and the `NaType` singleton `Na` that represents the absence of some value.

```py
Na: NaType = NaType()
"""Singleton 'no value'. Misses are values, never exceptions."""

type Maybe[V] = V | NaType
```

Example functions and types for working with `Maybe[V]` objects.

```py
from orcaset import Maybe, Na, isna, maybe

rate: Maybe[float] = maybe.some(0.1)
print(isna(rate))  # False
print(isna(Na))  # True

print(maybe.value_or(Na, 0.15))  # 0.15
print(maybe.value_or(rate, 0.15))  # 0.1


# Na propagating map
def double(x: float) -> float:
    return x * 2


maybe.map_some(double)(Na)  # Maybe[float]: Na
maybe.map_some(double)(rate)  # Maybe[float]: 0.2


# Na propagating map2
def divisable(x: float, y: float) -> float:
    return x % y == 0


maybe.map2_some(divisable)(Na, 2)  # Maybe[float]: Na
maybe.map2_some(divisable)(rate, 2)  # Maybe[float]: 0.2
```

The `maybe` module holds convenience `Na` propagating functions for `sum_some`, `sub_some`, `mul_some`, `div_some`, and `neg_some` as well as `combine_some` that is a `mapn` type function. It also has a `some` function that lifts a `V` into a `Maybe[V]` type.

## Basic structure

Models are build around unkeyed and keyed effect handlers that resolve values, trace dependencies, and cache values within an evaluation context. Effects are managed with generators that request values fro the evaluation context with `yield` and return their own resolved value.

```py
from orcaset import Effect, Fn, Val, get

# lift a value into an unkeyed rule
growth_rate = Val("Growth rate", value=0.05)
# create a new unkeyed rule that depends on the growth rate
shocked_growth_rate = Fn("Shocked rate", fn=lambda: (yield from get(growth_rate)) * 0.5)


# created an Fn unkeyed rule by decorating a function that can't fit in a lambda
@Fn.define("Contingent rate")
def contingent_rate() -> Effect[float]:
    base_rate = yield from get(growth_rate)
    if base_rate > 0.1:
        return base_rate + 0.2
    else:
        return base_rate
```

Values are resolved with a context. Each context caches all rule values, so they are NEVER recalculated within a context. For example, resolving `contingent_rate` only prints `Calculating contingent rate` the first time it is queried.

```py
from orcaset import Context

ctx = Context()
print(ctx.get(growth_rate))
# 0.05
print(ctx.get(shocked_growth_rate))
# 0.025
print(ctx.get(contingent_rate))
# Calculating contingent rate
# 0.05
print(ctx.get(contingent_rate))
# 0.05
```

`KeyedVal` and `KeyedFn` similarly lift mappings and functions that take a single argument into rules respectively. Resolve them using `get_at(rule, parameter)`.

## Time series

Create line items representing sequential values over time using `Series[Key, CellType, QueryType]`.

`Series` holds a rule with a lazy linked chain of `Key, CellType` pairs that are strictly increasing, non-overlapping by key and a `Key -> QueryType` query function that folds over the chain to return interpolated/aggregated values.

```py
from orcaset import Chain, Cons, Series

cons_tail = Cons(
    key=date(2026, 3, 31),
    value=Val("Constant", value=200.0),
    tail=Val("Cons end", None),
)
cons_head = Cons(
    key=date(2025, 12, 31),
    value=Val("Constant", value=100.0),
    tail=Val("Cons tail", cons_tail),
)
chain: Chain[date, float] = Val("Chain", value=cons_head)


def last(key: date, chain: Chain[date, float]) -> Effect[Maybe[float]]:
    """Get the last value <= key or Na if no such value exists"""
    head: Cons[date, float] | None = yield from get(chain)
    if head is None or key < head.key:
        return Na
    while head.key < key:
        tail = yield from get(head.tail)
        if tail is None:
            return (yield from get(head.value))
        head = tail
    return (yield from get(head.value))


series: Series[date, float, Maybe[float]] = Series("Constant", chain, last)

ctx = Context()
print(ctx.get_at(series, date(2024, 12, 31)))  # before the first period
# Na
print(ctx.get_at(series, date(2025, 12, 31)))  # in the first period
# 100.0
print(ctx.get_at(series, date(2026, 12, 31)))  # in the second period
# 200.0
print(ctx.get_at(series, date(2027, 12, 31)))  # after the second period
# 200.0
```

Series are typically defined by the the `Series.define` constructor that decorates an unfold step function or with combinators from the `ops` module.

```py
import math
from orcaset import YF, get_at, ops, period_union, query

quarter_offset = relativedelta(months=3, day=31)
initial_year = Period(date(2024, 12, 31), date(2025, 12, 31))
initial_value = 100.0
annual_growth_rate = 0.1


@Series.define("Line A", query.accrue(YF.cmonthly), seed=initial_year)
def line_a(period: Period) -> Effect[tuple[Period, float, Period]]:
    if period == initial_year:
        amount = initial_value
    else:
        prior: Maybe[float] = yield from get_at(
            line_a, period.from_start(-quarter_offset)
        )
        if isna(prior):
            raise ValueError(f"Missing prior-quarter line A for {period}")

        amount = prior * math.pow(1.0 + annual_growth_rate, YF.cmonthly(*period))
    return period, amount, period.from_end(quarter_offset)


line_b: Series[Period, Maybe[float], Maybe[float]] = ops.scale("Line B", line_a, -0.4)
line_c: Series[Period, Maybe[float], Maybe[float]] = ops.add(
    "Line C", line_a, line_b, merge_keys=period_union
)
```

`ops` has combinators for `map`, `map2`, `mapn`, `add`, `mul`, `neg`, `scale`, `sub` and `div`.
Use `orcaset.date_union` as the key merge function for date-keyed series.

The `query` module holds functions for querying over cell chains.
- `exact[K: Key, V](q: K, cells: Chain[K, V]) -> Effect[Maybe[V]]`: Return the value for the cell with `q == K` or `Na` if no exact match exists.
- `covered(q: Period, cells: Chain[Period, Maybe[float]]) -> Effect[Maybe[float]]`: Sum one or more cells that exactly tile `q` or return `Na` on any gap or partial overlap. Useful for over-time flows where partial periods should not be interpolated (e.g., historicals).
- `accrue[V: float | NaType](yf: DayCount) -> QueryFn[Period, V, Maybe[float]]`: Create a query function that accrues partial periods using `yf`. Use like `query.accrue(YF.cmonthly)` to query over-time flows. Returns `Na` if any part of the query range is outside the series' domain.
- `avg[V: float | NaType](yf: DayCount) -> QueryFn[Period, V, Maybe[float]]`: Create a query function that averages cell values over a query period. Use like `query.avg(YF.cmonthly)` to avgerage period-keyed stocks on an equal month duration basis. Returns `Na` if any part of the query range is outside the series' domain.

## Key selection

Line items are generally keyed by either `date` or `Period`.

- `Period`: Over-time values. Might either represent flows like income statement accruals or stocks that are applicable to a specific period like monthly sale prices.
- `date`: Point-in-time values. Might either represent flows like cash payments on a specific date or stocks like balance sheet items.

ALWAYS model debt, balances, capital accounts, and similar point-in-time values as a single date-keyed series. NEVER create separate series for beginning and ending period balances.

## Horizontal series composition

Horizontal composition extends or overrides a values for a series' domain. This applies to situations like projections from historicals, other disjoint segments, or overriding values for (part of) a series' domain.

See the [patterns.md](patterns.md) reference file for guidance on extending series domains with concat, append, extend type of functions.

## Outputs

Use the `stmt` and `formatter` modules for building and resolving structured views of line items. See the [output.md](output.md) reference file.

## Dependency tracking

`Context` objects record value dependencies for introspection and verification. See the [verification.md](verification.md) reference file for working with dependencies.