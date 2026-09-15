# Graph construction and query semantics

## Nodes and series

Imports for common models:

```python
from orcaset import (
    Context, Effect, Fn, Maybe, Period, Rule, Series, Thunk, Val,
    YF, get, get_at, isna, maybe, ops, period_union, query,
)
```

`Val(name, value)` is an adjustable leaf; `Fn(name, fn)` or `@Fn.define(name)` is a computed unkeyed node. `KeyedFn` supports a keyed formula without a series domain. `Series[K, V, W]` is a keyed rule with a discoverable domain and query semantics.

`Series.of(name, query_fn, pairs)` accepts a finite sequence of `(key, value)` pairs, or a rule supplying that sequence. Deferred values are `Thunk(fn)`; materialize a generator into a sequence before passing it to `of`.

For a lazy domain, `Series.unfold(name, query_fn, seed=state, step=fn)` calls a step returning `(key, value, next_state)` or `None`. `@Series.define(name, query_fn, seed=state)` is its decorator form. The step can return an `Effect` of that result:

```python
from datetime import date
from dateutil.relativedelta import relativedelta

MONTH = relativedelta(months=1)
first = Period(date(2028, 1, 1), date(2028, 2, 1))
opening = Val("Initial monthly sales", 250.0)
growth = Val("Monthly sales growth", 0.015)

@Series.define("Sales", query.accrue(YF.cmonthly), seed=first)
def sales(p: Period) -> Effect[tuple[Period, float, Period]]:
    if p == first:
        amount = yield from get(opening)
    else:
        prior = yield from get_at(sales, p.from_start(-MONTH))
        if isna(prior):
            raise ValueError(f"Missing prior sales for {p}")
        rate = yield from get(growth)
        amount = prior * (1.0 + rate)
    return p, amount, p.from_end(MONTH)
```

State should describe structural progress, such as a period, index, or remaining chain. For a financial recurrence, read the prior public node rather than carrying a resolved amount in state — demand `get_at(series, prior_key)` inside the step and inside `extend` continuations so each later cell stays connected to the base leaf in the dependency tree. Do not read the previous chain node's value rule with `get(node.value)`; the recurrence should query the public series. A `Thunk` seed can obtain a starting state from adjustable inputs when the head is first demanded. Later states are passed through unchanged.

A series' `.cells` is a `Chain[K, V]`, a rule resolving to `Cons(key, value, tail)` or `None`; `value` and `tail` are rules. Walk it with `yield from get(series.cells)`, then `yield from get(node.tail)`. Demand `node.value` only when needed. Bound walks of infinite chains.

## Query selection

| Financial meaning | Query |
| --- | --- |
| Exact observation, rich value, or exact schedule cell | `query.exact` |
| Balance held until the next observation | `query.last` |
| Flows that must exactly tile a requested interval | `query.covered` |
| Flows prorated over intersecting intervals | `query.accrue(yf)` |
| Levels averaged over intersecting intervals | `query.avg(yf)` |
| No event means zero | `query.exact_or(0.0)` |

`query.accrue(YF.cmonthly)` weights overlaps on a calendar-month basis; use the specified day count, not an interchangeable approximation. Actual-day weighting can use `lambda start, end: (end - start).days`. Accrual returns an exact cell unchanged and otherwise weights each contributing value by overlap measure / cell measure. `covered` rejects incomplete or partial tiling. `last` returns `Na` before the first observation unless a default query is chosen.

`Period(start, end)` has `start < end`; `p.from_end(offset)` forms the next interval, and `p.from_start(-offset)` the preceding interval. For month-end schedules use `relativedelta(months=1, day=31)` to avoid drifting after February. Period ordering means entirely before, so don't sort overlapping periods as if the order were total.

Ratios and margins should normally be computed from the queried numerator and denominator. Summing monthly ratios is not a quarterly ratio. Averaging levels and accruing flow amounts have different meanings.

## Composition

```python
costs = ops.scale("Cost of sales", sales, -0.4)
profit = ops.add("Gross profit", sales, costs, merge_keys=period_union)
margin = ops.div("Gross margin", profit, sales, merge_keys=period_union)
```

Use `date_union` for date-keyed combinations. `ops.map(name, source, fn=...)`, `ops.map2(name, left, right, fn=..., merge_keys=...)`, and `ops.mapn(name, sources, fn=..., merge_keys=...)` transform query answers and permit effectful callbacks. Each source is queried at the requested key, including off-spine keys. `ops.scale` also accepts a `Rule[float]` factor.

Float arithmetic operations propagate `Na`; `fill=` substitutes per missing source only when that is the intended economics. `maybe.map_some(fn)` and `maybe.map2_some(fn)` lift typed functions over `Maybe` values. Use `isna` to narrow a required input before arithmetic. Empty `maybe.sum_some()` returns `Na`; start an economically empty aggregate at `0.0` explicitly.

Compose each line from its stated inputs. When the model defines a named subtotal, downstream lines consume that node — build income from `gross_profit` rather than recombining `revenue` and `cogs`. Likewise, a derived line is an `ops` map over its inputs, not a separate `unfold` that re-creates their schedule.

`map_cells` and `scan_cells` transform chains rather than answers. Their callbacks receive source value rules and return plain values or `Thunk`s, not effect generators. Wrap effectful mapped values in `Thunk`. Use structural operations for changed domains, adjacent observations, or nested schedules, rather than replacing straightforward `ops` formulas.
