# Modeling core

## The graph and the chain

An Orcaset model consists of named `Rule` and `KeyedRule` nodes. `Cell` is an unkeyed rule. `Series[K, V, W]` is a keyed rule where:

- `K` is both the cell-key and query-key type;
- `V` is the stored cell-value type;
- `W` is the query-answer type.

A series holds `Cells[K, V]`, a rule resolving either `Cons(key, cell, tail)` or `None`. Both `cell` and `tail` are rules. A context can therefore discover only as much of a domain as a query needs, without forcing unrelated values.

Keep public model outputs as Orcaset nodes. Do not export a calculated list, dictionary, dataframe, or helper that evaluates through a hidden context. Inside model computation, every upstream read is an effect:

```python
rate = yield from get(growth)
prior = yield from get_at(revenue, prior_period)
node = yield from get(source.cells)
```

The context memoizes each rule/key and records these dependency edges. Do not add `lru_cache`, a value dictionary, or an imperative running total for values that belong in the graph.

## Construct a series

Use `Series.of` for finite, already-known pairs. The iterable is materialized when the series is built, but `Thunk` values remain deferred:

```python
history = Series.of(
    "Revenue history",
    covered,
    [(q1, 100.0), (q2, Thunk(load_q2))],
)
```

Use `Series.unfold` when the domain is lazy, infinite, stateful, or determined by other rules. Its step receives state and returns `(key, value, next_state)` or `None`; the step itself may be effectful:

```python
@Series.define("Revenue", accrue(YF.cmonthly), seed=first_period)
def revenue(period: Period) -> tuple[Period, float | Thunk[float], Period]:
    def value() -> Effect[float]:
        prior = yield from get_at(revenue, period.shift(-YEAR))
        return 100.0 if isna(prior) else prior * 1.05

    return period, Thunk(value), period.from_end(YEAR)
```

`@Series.define` is the decorator form of `Series.unfold`; use it when the step must refer to the series being defined. State is passed explicitly, so the old loop-factory closure pattern is unnecessary.

Keys must be strictly ascending. For `Period`, `a < b` means `a.end <= b.start`; overlapping periods are mutually incomparable and cannot be emitted successively. Stop a finite unfold with `None`.

## Defer values deliberately

An unfold result treats only `Thunk(fn)` as deferred computation. Every other object—including a callable—is a literal value. Wrap computations that demand other rules:

```python
def value() -> Effect[float]:
    source_value = yield from get(source)
    return source_value * 2.0

return key, Thunk(value), next_state
```

Do not put a live generator in the value slot; Orcaset raises `TypeError`. Use a plain value when it is already known. Keeping values deferred allows key-only walks to remain cheap and prevents structure inspection from causing I/O or model evaluation.

## Compose answers with `ops`

Use answer-level operations for calculations that query their sources at the same key:

```python
costs = ops.scale("Costs", revenue, -0.45)
gross_profit = ops.add(
    "Gross profit",
    revenue,
    costs,
    merge_keys=period_union,
)
```

- `ops.map_values` maps one source answer and retains its spine.
- `ops.map2` combines two generic `Maybe`-answer series with a typed function.
- `ops.combine`, `add`, and `mul` combine one or more float series.
- `ops.sub` and `div` are binary; `ops.neg` and `scale` keep one source's domain.

The combined spine is the lazily merged union, but each query delegates to every source at that exact key. A key need not be on the spine. Each source's own query semantics still apply. The arithmetic operations propagate `Na` by default; `fill=` substitutes for each missing source only when that policy is economically intended.

Do not invent a source dependency merely to borrow its keys. A fixed schedule with an independent domain should have its own chain and meet other lines only in a downstream operation.

## Transform structure only when structure changes

Use chain helpers when the output's domain or structural state truly depends on another chain:

- `map_cells(name, source, fn)` preserves keys and passes each source `Rule[V]` to `fn` without forcing it. Return `Thunk` if the mapped value must demand that rule.
- `scan_cells(name, source, seed=..., fn=...)` carries structural state while mapping one-for-one. Its accumulator is for information such as the prior key or an index—not resolved financial values.
- `merge_cells(name, chains, merge, cell)` lazily re-tiles a union with one pending head per chain and never forces source cells. Prefer `date_union` or `period_union`; a custom `KeyMerge` must obey the documented refold law.
- `unfold_cells` builds a standalone continuation or another raw chain.

Wrap a transformed chain with `Series(name, cells, query)`. Do not use `scan_cells` as an eager value fold: a rollforward cell should use its carried prior key to demand the prior public balance through `get_at`.

## Extend or append a chain

`Series.extend` continues a base chain only when a walk reaches its frontier:

```python
combined = Series.extend(
    "Revenue",
    covered,
    base=history.cells,
    cont=forecast_cells,
)
```

`forecast_cells(last)` receives the last base key, or `None` when the base is empty. It is not invoked for queries that stop inside the base. Leading continuation nodes not entirely after the last base key are clipped without forcing their values. The base must terminate for the continuation to become reachable.

Use `Series.append` when the continuation chain is fixed rather than built from the frontier. Both operations produce one chain governed by the single query supplied to the resulting series; test queries on each side and across the seam.

## Custom queries

A `QueryFn[K, V, W]` receives `(query_key, cells)` and returns `W` directly or through an `Effect[W]`. Walk tails with `yield from get(...)`, force only cells needed for the answer, stop once ascending order proves later keys irrelevant, and define misses explicitly. Prefer shipped queries when their contracts fit.
