# Orcaset

This branch holds an experimental version of `orcaset` with a free monad implementation.

The library is layered:

- **Core `F`** (`f.py`, `context.py`): an inert `Pure | Delay | Map | Apply | Bind` AST evaluated by an iterative interpreter with a per-`Context`, id-keyed cache.
- **Series** (`series.py`): a line item is a `Series[K, V, Q]` — an ordered stream of `(key, F[value])` cells plus a query convention: a `select` function that narrows the stream to the (possibly clipped) cells answering a query, and a `reduce` function that collapses them to one value. `series.query(q)` is the sole retrieval interface and `series.select(q)` is its audit view; both return one memoized node per `(series, query)`, so repeated calls are O(1) and shared questions are shared graph nodes.
- **Conventions** (`conventions.py`): standard select/reduce pairs — `flow(...)` for `Period`-keyed flows (day-count proration over partial periods, summed) and `keyed(...)` for exact-keyed lookups — plus the pieces (`clip_daily`, `exact`, `total`, `only`, `only_or`) to compose your own.
- **Model**: plain objects wiring series together by reference. Construct each series once; evaluate in a `Context` per scenario. Recursive line items query themselves (`series.query(prior_window)` inside the cell factory), so dependencies are stated as key windows rather than stream positions and survive re-keying (e.g. monthly to quarterly).

Clone project and check out this branch:

```sh
git clone -b ref-monadic https://github.com/Orcaset/orcaset-py.git
```

## Examples

- [recursion_err](./examples/recursion_err.py): Deep chaining (no longer causes recursion errors) and a self-querying integer series
- [recurse_spans](./examples/recurse_spans.py): Recursive revenue growth series keyed by `Period`, defined by querying the prior period's window
- [fwd_recursion](./examples/fwd_recursion.py): Forward self-reference (backsolve from a terminal) and partial-period self-queries
- [year_ago](./examples/year_ago.py): Quarterly historicals extended by year-ago window queries, arbitrary date-window aggregation, and the `select` audit view
- [capex](./examples/capex.py): Capex > amort schedule per cohort > merged total amort