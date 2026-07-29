# Orcaset — Financial Models for Computers

## Series

A `Series` is a `Rule` with an explicit time domain: a demandable answer (`ctx.demand(series, q)`) plus a public key stream (`series.keys`) — a lazy, strictly ascending, possibly infinite stream of keys (dates, periods, ...), buffered per `Context` so it can be re-scanned cheaply. Iterating keys never forces values.

`GridSeries` is the workhorse implementation. It separates three things:

- **Cells** (private) — the value at each domain key, memoized per key. Recurrences live here: a cell may read the prior cell ("last value × growth") or fetch any other rule.
- **Selection** — which grid keys are relevant to a query.
- **Reduction** — how fetched cells combine into an answer (prorate, interpolate, aggregate).

Query semantics are fixed per *series*, not per call — a 30/360 accrual stream can't accidentally be read with actual/actual. All three ingredients are constructor state: `value_at` is the instance data, `select`/`reduce` are the (matched) query semantics. Construction helpers pair them so line items compose conventions inline instead of importing a class per combination:

```python
def revenue_at(s, key):  # grid definition; `s.cell(k)` reads this series' own grid
    prior = yield from s.cell(key.shift(months=-1))
    return 100.0 if isna(prior) else prior * 1.02


revenue = flow("revenue", monthly_keys, revenue_at, yf=YF.cmonthly)  # calendar-month flow
rent = flow("rent", quarterly_keys, rent_at, yf=YF.cmonthly)  # quarter = 1/4 year
accrual = flow("accrual", accrual_keys, accrual_at, yf=YF.thirty360)  # 30/360 proration
balance = level("balance", monthly_keys, bal_at, yf=YF.act360)  # time-weighted average

ctx = Context()
ctx.demand(revenue, Period(date(2026, 1, 31), date(2026, 3, 15)))  # prorates across cells
```

Custom semantics are just functions passed to `GridSeries` directly — the generics tie `select` and `reduce` together over `[Q, K, V, W]`:

```python
custom = GridSeries("custom", keys, value_at, select=my_select, reduce=my_reduce)
```

The same construction can be written as a decorator, with arguments ordered
as `keys`, `select`, `reduce`, and `label`:

```python
@grid(keys, my_select, my_reduce, "custom")
def custom(reader, key):
    return value_at(reader, key)
```

Derived series transform *answers*, not cells. `series.map(name, fn)` builds a `MapSeries` that answers `fn(source answered at q)` for every query — resolution is fully delegated to the source, whose query semantics apply before `fn`. `fn` sees the raw answer (typically `Maybe`) and owns the miss policy:

```python
taxed = revenue.map("taxed", lambda v: Na if isna(v) else v * 0.79)
```

`MapNSeries` applies the same answer-level composition to a nonempty tuple of
homogeneous sources. Every source is queried at the requested `q`; a supplied
`merge_keys` function lazily constructs the derived series' public domain:

```python
profit = MapNSeries(
    "profit",
    (revenue, cogs, opex),
    add_values,
    merge_keys=period_union,
)
```

`period_union` is the standard merger for `Period` domains. `add_values`
adds `Maybe[float]` answers while propagating `Na`; use
`combine_values(values, operator)` for the same policy with another binary
operation.

Conventions and guarantees:

- **Misses are values, never exceptions.** Anything outside the domain resolves to the `Na` singleton; results are `Maybe[V]`. Use `isna(v)` to test (it type-narrows); `bool(Na)` raises by design.
- **Shared domains:** pass another series' `keys` rule to a constructor (`MySeries("costs", revenue.keys, ...)`) when the grid is definitionally the same; both series then share one key buffer per context and traces show the shared dependency.
- **Ascending keys are enforced** lazily as the stream is first pulled; misordered domains raise `ValueError`.

Every cross-layer read goes through `fetch`, so `ctx.dependencies(series, q)` shows exactly which grid cells (and upstream rules) produced a number.

## License

Orcaset is licensed under the Server Side Public License. You can freely use it to build internal models for underwriting, valuation, risk, or other analysis. See [LICENSE](./LICENSE) for details.
