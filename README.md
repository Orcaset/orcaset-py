# Orcaset

This branch holds an experimental version of `orcaset` with a free monad implementation.

The library is layered:

- **Core `F`** (`f.py`, `context.py`): an inert `Pure | Delay | Map | Apply | Bind` AST evaluated by an iterative interpreter with a per-`Context`, id-keyed cache.
- **Absence** (`maybe.py`): `query` is total — any query may be asked of any series — so it answers `Maybe[V]`, a value or `MISSING`. A cell exists only where data exists, so absence in a stream is positional; `MISSING` appears only as an answer. Every consumer states a policy: `strict` (absence is an error), `propagate` (absence spreads), `fill` (absence is a known identity), plus `unwrap`/`or_else` at the point of use.
- **Series** (`series.py`): a line item is a `Series[K, V, Q]` answering `query(q) -> F[Maybe[V]]`.
  - A `LeafSeries` holds an ordered stream of `(key, F[value])` cells plus a convention: `select` narrows the stream to the (possibly clipped) cells answering a query, and `reduce` — which is total, so an empty selection still answers — collapses them to one value. `leaf.select(q)` is the audit view behind `leaf.query(q)`.
  - `map`/`map_maybe`/`map2`/`MapNSeries`/`merge` build *views*: they transform and combine complete answers, so they have no cells and no convention, and their provenance is the child query nodes. Evidence lives at leaves, which is where the arithmetic on cells happens.
  - `resample`/`rekey` bridge back: they tabulate any series on a new key grid, producing a leaf whose cells are the source's query nodes. That is how a monthly line becomes an annual one, and how a view regains cells.
  - Every question is one memoized node per `(series, query)` — `query`, `select`, `keys` — so repeated calls are O(1) and shared questions are shared graph nodes. Series memoize *nodes*; values are cached per `Context`.
- **Conventions** (`conventions.py`): select/reduce pieces (`clip_daily`, `exact`, `sum_cells`, `only`, `only_or`) to compose with `LeafSeries.from_cells` / `from_pairs`. A common flow line is `clip_daily()` with `sum_cells(0.0)` (day-count proration; an uncovered window is `0.0`); an exact-keyed line is `exact()` with `only()` (an absent key answers `MISSING`).
- **Model**: plain objects wiring series together by reference. Construct each series once; evaluate in a `Context` per scenario. Recursive line items query themselves (`series.query(prior_window)` inside the cell factory), so dependencies are stated as key windows rather than stream positions and survive re-keying (e.g. monthly to quarterly). Such a cell receives a `Maybe` and resolves it — seeding on `MISSING` is how a recursion states its base case.

Clone project and check out this branch:

```sh
git clone -b ref-monadic https://github.com/Orcaset/orcaset-py.git
```

## Examples

- [recursion_err](./examples/recursion_err.py): Deep chaining (no longer causes recursion errors) and a self-querying integer series
- [recurse_spans](./examples/recurse_spans.py): Recursive revenue growth series keyed by `Period`, defined by querying the prior period's window
- [fwd_recursion](./examples/fwd_recursion.py): Forward self-reference (backsolve from a terminal) and partial-period self-queries
- [year_ago](./examples/year_ago.py): Quarterly historicals extended by year-ago window queries, arbitrary date-window aggregation, the `select` audit view, and `resample` onto an annual grid
- [capex](./examples/capex.py): Capex > amort schedule per cohort > cohorts merged with `fill(0.0, add)` into total amort
