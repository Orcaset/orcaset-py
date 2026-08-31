# Runtime and debugging

## Materialize values

Outside model computation, resolve unkeyed and keyed rules through a context:

```python
ctx = Context()
rate = ctx.get(growth)
revenue_value = ctx.get_at(revenue, period)
debt_value = ctx.get_at(debt, period.end)
```

Inside model computation, use `yield from get` and `yield from get_at` instead.
Do not call context methods from factories and do not hide a context in a
series-building helper.

One context represents one run. It memoizes each rule/key and records the
dependencies traversed during that run. Reuse it for related output and
diagnostics. Create a fresh context after changing a `Cell` function, source
function, or scenario configuration.

For structured output, compose `Group` and `Total` rows into `Stmt`. Materialize
period rows with `values_for_periods` or mixed period/date rows with `values`,
then format the result with `fixed_width_table`, `markdown_table`, or
`csv_table`. Keep statement presentation downstream of the queryable model
nodes; formatted output is not a model export.

## Trace dependencies

Use the same context that produced the value:

```python
tree = ctx.dependencies(revenue, period)
print(tree)

assumption_tree = ctx.rule_dependencies(growth)
```

The returned `DepNode` exposes `name`, `key`, `value`, and `deps`. A correct
trace should show economically meaningful upstream nodes. A missing expected
edge often reveals local state, a hard-coded value, a plain Python lookup, or
an eagerly materialized cache.

## Debug in this order

1. Confirm the exported object is the expected Orcaset rule or series.
2. Confirm query and cell key types match and inspect their exact boundaries.
3. Query the immediate upstream node at the same relevant key.
4. Check the series query contract and whether `Na` or zero is intended.
5. Print the dependency tree and locate the first surprising node or missing
   edge.
6. For a cycle, inspect the cycle path or convergence history.
7. Retry in a fresh context if any adjustable input or source function changed.
8. Add a focused regression assertion before modifying the formula.

Common symptoms:

- `'dict'/'list' object has no attribute 'id'`: a model node was replaced by a
  Python container.
- `Na` at a valid key: inspect key boundaries, query choice, and the first
  missing upstream value; do not immediately plug zero.
- Stale scenario output: the same context was reused after changing a `Cell`.
- Missing dependency edge: a value was hard-coded, read directly, accumulated
  locally, or materialized outside the graph.
- `TypeError` comparing `Period` and `date`: a flow and stock domain were mixed.
- Generator-valued answer: a factory returned a generator instead of yielding
  demands and returning its final value.
