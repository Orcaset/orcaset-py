# Runtime and debugging

## Resolve model values

Outside model computation, use a context:

```python
ctx = Context()
rate = ctx.get(growth)
revenue_value = ctx.get_at(revenue, period)
debt_value = ctx.get_at(debt, period.end)
```

Inside a rule, query, unfold step, or thunk, use `yield from get` and `yield from get_at` instead. Do not call context methods inside model computation or store a context in a model object.

One context represents one run. It memoizes every resolved rule/key and keeps the dependencies traversed during that run. Reuse it for related output and diagnostics. Create a fresh context after changing a `Cell.fn`, data-source function, or scenario configuration.

Keep evaluation and reporting downstream from model definition. Materialize only the requested keys into a table, JSON object, or display structure; formatted output is not a model export. Do not evaluate unbounded series.

For a structured income or cash-flow view, wrap the already-defined series in `stmt.Stmt`, `stmt.Total`, and `stmt.Group`, then call `values_for_periods` or `values_for_dates` and pass the `stmt.StatementResult` to `formatter.fixed_width_table`, `formatter.markdown_table`, or `formatter.csv_table`.

## Inspect a domain without forcing values

`keys_until(cells, stop)` walks keys through a bound without forcing their cell values or walking past the bound. Because it is effectful, resolve it through a temporary rule:

```python
probe = Cell("Revenue keys", lambda: keys_until(revenue.cells, stop))
keys = ctx.get(probe)
```

For custom inspection, start with `node = yield from get(series.cells)` and advance with `yield from get(node.tail)`. Demand `node.cell` only when the value is actually needed. With direct unfold values, a key walk also computes those values; this is expected. Investigate a missing `Thunk` only when traversal must precede value resolution or the model requires key-only walks to avoid computation or I/O.

## Verify dependencies with targeted queries

Use `Context.depends_on(source, target)` to check whether an output depends directly or transitively on an expected input. Use `Context.path_to(source, target)` when you need to explain the connection. Do not manually walk, expand, or print full dependency trees for model verification; large graphs can make that prohibitively expensive.

Use the same context that produced the answer. Both methods resolve the source automatically, so they also work in a fresh context. Pass a keyed `Series` or `KeyedRule` as `(rule, key)` and an unkeyed `Rule` or `Cell` directly:

```python
assert ctx.depends_on((revenue, period), growth)
assert ctx.depends_on((debt, period.end), (debt, period.start))

path = ctx.path_to((revenue, period), growth)
assert path is not None
for node in path:
    print(node.name, node.key, node.value)
```

Choose source/target pairs that reflect the model's intended formulas; these examples assume revenue reads growth and closing debt reads opening debt. Check representative keys and relevant expected or forbidden dependencies, rather than enumerating every reachable node.

`depends_on` returns a boolean; direction is from the consuming output to its upstream input. `path_to` returns one shortest demand path as a tuple of `DepNode` objects ordered from source to target, or `None` if no path exists. Path nodes have `name`, `key`, and `value`, with empty `deps`; there is no subtree to recurse into. Pass `structural=True` to `path_to` to retain internal chain nodes when investigating unfold tails, domain decisions, extension frontiers, or merges.

These checks describe dependencies demanded in this run, not all possible scenario branches. A `(series, key)` target matches its query cell or its stored cell if that key was already unfolded; looking up the target does not force additional unfolding. A node depends on itself only through a demand cycle. Use a fresh context after changing inputs, and retain numerical and economic reconciliation checks alongside graph assertions.

A missing expected dependency often reveals a hard-coded value, direct function call, local accumulation, or eagerly materialized cache. Extra `.cells` and `.tail@...` nodes in a structural path show scheduler mechanics, not extra economic formulas.

## Debug in this order

1. Confirm the export is the intended `Rule`, `KeyedRule`, or `Series`.
2. Confirm its `Series[K, V, W]` key, cell, and answer types.
3. Inspect exact key boundaries and walk only enough of the domain to locate the query.
4. Query each immediate upstream node at the relevant key.
5. Check the query function and whether `Na`, a default, or an error is intended.
6. Check the suspected source/target relationship with `depends_on`; inspect `path_to` if needed, using `structural=True` if the domain or frontier is suspect.
7. For a cycle, inspect the cycle path or convergence history.
8. Retry in a fresh context if any mutable input function changed.
9. Add a focused regression assertion before changing the formula.

Common symptoms:

- `Na` at a valid-looking key: inspect the exact boundaries, source query semantics, and first missing dependency; do not immediately substitute zero.
- `ValueError` about ascending keys: the unfold repeated, overlapped, or moved backward from its prior key.
- A callable returned as the answer: callables are literal values unless wrapped in `Thunk`.
- `TypeError` mentioning a live generator: deferred computation was put in the value slot without `Thunk`.
- A `.tail@...` `CycleError`: domain construction demanded a query that needs the same unresolved tail.
- Stale scenario output: a context was reused after changing `Cell.fn` or a source function.
- Missing dependency edge: a value bypassed `get`/`get_at`.
- Unexpected `Na` after `ops.add` or `mul`: every source is queried at the same key and the default arithmetic policy propagates a source miss.
