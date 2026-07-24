# Orcaset

This branch holds an experimental version of `orcaset` with a free monad implementation.

The library is layered:

- **Core `F`** (`f.py`, `context.py`): an inert `Pure | Delay | Map | Apply | Bind` AST evaluated by an iterative interpreter with a per-`Context`, id-keyed cache.
- **Series** (`series.py`): a line item is a `Series[K, V]` — an ordered stream of `(key, F[value])` cells. Each series owns one stream node and memoizes one address node per key (`series.at(key)`), so shared cells are shared graph nodes.
- **Model**: plain objects wiring series together by reference. Construct each series once; evaluate in a `Context` per scenario.

Clone project and check out this branch:

```sh
git clone -b ref-monadic https://github.com/Orcaset/orcaset-py.git
```

## Examples

- [recursion_err](./examples/recursion_err.py): Deep chaining (no longer causes recursion errors) and a recursive integer series
- [recurse_spans](./examples/recurse_spans.py): Recursive revenue growth series keyed by `Period`
- [fwd_recursion](./examples/fwd_recursion.py): Forward self-reference (backsolve from a terminal) and partial-period aggregation
- [year_ago](./examples/year_ago.py): Quarterly historicals extended by year-ago references, plus arbitrary date-window aggregation with `between`
- [capex](./examples/capex.py): Capex > amort schedule per cohort > merged total amort