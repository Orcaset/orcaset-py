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

Use `Series.of` for a sequence of pairs or a `Rule` supplying one. A rule source is resolved when the head is demanded. Wrap generators and `enumerate` results in a list or tuple before passing or returning them. Individual `Thunk` values remain deferred:

```python
history = Series.of(
    "Revenue history",
    query.covered,
    [(q1, 100.0), (q2, Thunk(load_q2))],
)
```

Use `Series.unfold` when the domain is lazy, infinite, stateful, or determined by other rules. Its step receives state and returns `(key, value, next_state)` or `None`; the step itself may be effectful:

```python
start_date = Cell("Forecast start", lambda: date(2027, 1, 1))

def initial_period() -> Effect[Period]:
    start = yield from get(start_date)
    return Period(start, start + YEAR)

@Series.define("Revenue", query.accrue(YF.cmonthly), seed=Thunk(initial_period))
def revenue(period: Period) -> Effect[tuple[Period, float, Period]]:
    amount = yield from get_at(source_revenue, period)
    if isna(amount):
        raise ValueError(f"missing source revenue for {period}")
    return period, amount * 1.05, period.from_end(YEAR)
```

`@Series.define` is the decorator form of `Series.unfold`; use it when the step must refer to the series being defined. A `Thunk` seed is resolved once when the head node is first demanded, so its dependencies can determine the initial state and domain. Later states returned by the step are passed through verbatim. State is passed explicitly, so the old loop-factory closure pattern is unnecessary.

Bare rules and callables in seed and unfold value slots remain data. To resolve a rule as the initial state, use `seed=Thunk(lambda: get(start_date))`; the lambda returns an effect, so it does not need its own `yield from`. The same seed convention applies to `unfold_cells` and `scan_cells`.

Keys must be strictly ascending. For `Period`, `a < b` means `a.end <= b.start`; overlapping periods are mutually incomparable and cannot be emitted successively. Stop a finite unfold with `None`.

## Prefer direct values; defer only when needed

`Series.define`, `Series.unfold`, and `unfold_cells` accept steps returning `tuple[K, V | Thunk[V], S] | None`, either directly or through `Effect`. Prefer returning `V`: perform dependency reads with `yield from get(...)` or `yield from get_at(...)` in the step, then return the computed value. The step is already lazy and runs when its chain node is demanded.

Use `Thunk[V]` when the `Cons` must become available before its value can resolve. For example, a future self-reference may need to traverse the current node to reach a later key. Check the actual traversal dependencies: neither a self-reference nor an effectful read by itself establishes a need for `Thunk`. Deferral is also appropriate when a required key-only walk must avoid value computation or I/O.

An unfold result treats only `Thunk(fn)` as deferred computation. Every other object—including a callable—is a literal value. When separate value deferral is required:

```python
def value() -> Effect[float]:
    source_value = yield from get(source)
    return source_value * 2.0

return key, Thunk(value), next_state
```

Do not put a live generator in the value slot; Orcaset raises `TypeError`. An effectful step yielding dependencies and returning a tuple containing `V` is valid; returning a generator as that tuple's value is not. The direct-value preference applies to unfold steps; callbacks such as `map_cells` and `scan_cells` do not accept effectful callback results, so their effectful value computations still need `Thunk`.

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

## Join or extend series

Use `Series.flatten` when joined segments must retain their own query rules, with `continue_series` when the next segment depends on where the base ends. Use `Series.extend` to continue raw cells under one shared query policy. Read [series-composition.md](series-composition.md) for selection, seam behavior, and lazy continuation patterns.

## Custom queries

A `QueryFn[K, V, W]` receives `(query_key, cells)` and returns `W` directly or through an `Effect[W]`. Walk tails with `yield from get(...)`, force only cells needed for the answer, stop once ascending order proves later keys irrelevant, and define misses explicitly. Prefer shipped queries when their contracts fit.
