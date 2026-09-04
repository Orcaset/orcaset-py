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

For a structured income or cash-flow view, wrap the already-defined series in `Stmt`, `Total`, and `Group`, then call `values_for_periods` or `values_for_dates` and pass the `StatementResult` to `fixed_width_table`, `markdown_table`, or `csv_table`.

## Inspect a domain without forcing values

`keys_until(cells, stop)` walks keys through a bound without forcing their cell values or walking past the bound. Because it is effectful, resolve it through a temporary rule:

```python
probe = Cell("Revenue keys", lambda: keys_until(revenue.cells, stop))
keys = ctx.get(probe)
```

For custom inspection, start with `node = yield from get(series.cells)` and advance with `yield from get(node.tail)`. Demand `node.cell` only when the value is actually needed. A key walk that triggers source I/O or value calculation usually indicates a missing `Thunk` or a structural step that is doing value work.

## Trace dependencies

Use the same context that produced the answer:

```python
tree = ctx.dependencies(revenue, period)
print(tree)

assumption_tree = ctx.rule_dependencies(growth)
```

The returned `DepNode` has `name`, `key`, `value`, and `deps`. By default, Orcaset folds internal cell-chain traversal nodes so the tree emphasizes economic dependencies. Pass `structural=True` to either trace method when debugging unfold tails, domain decisions, extension frontiers, or merges.

A missing expected edge often reveals a hard-coded value, direct function call, local accumulation, or eagerly materialized cache. Extra `.cells` and `.tail@...` nodes in a structural trace show scheduler mechanics, not extra economic formulas.

## Debug in this order

1. Confirm the export is the intended `Rule`, `KeyedRule`, or `Series`.
2. Confirm its `Series[K, V, W]` key, cell, and answer types.
3. Inspect exact key boundaries and walk only enough of the domain to locate the query.
4. Query each immediate upstream node at the relevant key.
5. Check the query function and whether `Na`, a default, or an error is intended.
6. Print the default dependency tree; use `structural=True` if the domain or frontier is suspect.
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
