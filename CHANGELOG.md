# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the version is `0.x`, the public API is considered experimental and may
change between minor releases.

## [Unreleased]

The series core has been rebuilt on a lazy cons-chain representation. The
period/date convenience layers, statements, and formatters have been removed
pending a rebuild on the new core.

### Added

- `Cons(key, cell, tail)` and `Cells[K, V]` (a `Rule` resolving the first
  `Cons` or `None`). Each `tail` is an ordinary memoized rule that may demand
  other rules, so value-dependent domains are legal anywhere in a walk and
  exhaustion is an explicit `None`.
- `unfold_cells(name, seed=, step=)` builds a chain from a state-stepping
  function (`UnfoldFn`), replacing loop-variable capture with parameter
  passing. Keys must be strictly ascending; violations raise `ValueError`.
- `map_cells(name, source, fn)` transforms cells one-for-one without forcing
  their values; `scan_cells(name, source, seed=, fn=)` additionally carries
  structural accumulator state.
- `Thunk(fn)` nominally marks a deferred cell value in an unfold result. Any
  other value, including callables, is stored as-is; a live generator raises
  `TypeError`.
- `Series.unfold`, `Series.extend`, `Series.append`, `Series.of` (literal
  pairs), and the `@Series.define(name, query, seed=)` decorator for
  self-referential bodies.
- `Series.from_rule(name, query, pairs)` lazily builds a finite series from an
  effectful rule that resolves a sequence of key/value pairs.
- `extend_cells(name, base, cont)` continues a chain lazily at its frontier.
  `cont` receives the last base key (`None` when empty), is invoked only when
  a walk exhausts the base, and its leading nodes not entirely after the last
  base key are clipped without forcing their cells. `append_cells(name, first,
  then)` is the fixed-continuation form.
- `extend_period_series(name, base, cont, combine)` preserves the base and
  continuation query policies, splitting cross-frontier queries and combining
  their answers.
- `merge_cells(name, chains, merge, cell)` and `KeyMerge[K]`: merge ascending
  chains into one chain whose keys re-tile their union, with one pending head
  of lookahead per operand and source cells never forced. `merge` must satisfy
  the refold law (`merge(piece, head) == (piece, None, rest)`); violations
  raise `ValueError`.
- `ops` module with `combine(name, sources, fn=, merge_keys=)` and the
  arithmetic ops `add`/`mul` (n-ary) and `sub`/`div` (binary). Every query,
  on or off the merged spine, delegates to each source at the same key and
  passes the `Maybe[float]` answers to `fn`; the result's chain is the merged
  union so it is a valid `extend` continuation. `filled(fn, fill)` lifts a
  float fold to `Maybe` answers; `fill=` on each op substitutes that value for
  `Na` before the arithmetic (default propagates `Na`). `div` by zero raises.
- `ops.map_values(name, source, fn=)` maps `fn` over a series' answers,
  keeping the source's spine; every query delegates to the source at the same
  key so cells and off-spine queries honor the source's own query semantics.
  `ops.neg(name, source)` is the `Na`-propagating negation built on it.
- `ops.map2(name, left, right, fn=, merge_keys=)` maps a typed binary
  function over two generic series without restricting values to floats.
- `ops.add_scalar`, `ops.sub_scalar`, `ops.mul_scalar`, and `ops.div_scalar`
  provide `Na`-propagating scalar arithmetic over a source's own domain.
- `ops.period` and `ops.date` provide domain-bound `add`, `mul`, `sub`, `div`,
  and `map2` constructors without a repeated `merge_keys=` argument.
- `keys_until(cells, stop)` collects keys through `stop` without forcing
  cells or a past frontier.
- `first_key`, finite-only `last_key`, and bounded `collect_keys` inspect cell
  chain frontiers without forcing values.

### Changed

- `Series[K, V, W]` replaces `Series[Q, K, V, W]`: the query type is the key
  type. Every shipped query, combinator, and example already bound `Q = K`,
  and `combine`/`extend` require it (they query sources at domain keys), so
  the separate parameter only restated the invariant. `QueryFn[K, V, W]`
  likewise drops `Q`.
- `QueryFn` now receives `Cells[K, V]` (the chain rule) rather than an
  iterable of `(key, rule)` pairs, and walks it with `get(...)`.
- `exact` and `last` are effectful folds over the chain; behavior is
  unchanged (`Na` on a miss; `last` never forces a cell strictly before a
  later candidate).
- `accrual(yf)` and `covered` are effectful folds over `Cells[Period,
  Maybe[float]]` and now propagate `Na` from any contributing cell (an exact
  hit still passes the cell through unchanged). Series with plain `float`
  cells continue to type-check.
- `period_union` and `date_union` are now binary `KeyMerge` functions
  `(left, right) -> (piece, rest_left, rest_right)` for use with
  `merge_cells`/`ops`, rather than eager iterators over whole domains.

### Removed

- `BaseSeries`, `MapSeries`, `Map2Series`, `MapNSeries`, `MapItemsSeries`,
  `CellStream`, `CellFactory`, `CellsFn`, and `Replayable`. Derived series are
  built with `ops.combine` or by wrapping an exposed chain
  (`Series(name, other.cells, query)`).
- `PeriodSeries`, `PeriodSeriesBase`, `PeriodMapSeries`, `PeriodMap2Series`,
  `PeriodExtendSeries`, `DateSeries`, `DateSeriesBase`, `DateMapSeries`,
  `DateMap2Series`, `DateExtendSeries`, and the `scan`/`paired` transforms.
- `exact_or` and `accrual_or`. Misses answer `Na` and propagate; substituting
  a default belongs at the point of use (`value_or`, `ops.filled`), not in the
  query.
- `Stmt`, `Group`, `Total`, `StatementResult`, the `*Row`/`*Value` types, and
  the `formatters` module (`fixed_width_table`, `markdown_table`, `csv_table`,
  `ValueFormatter`, `DateFormatter`).

## [0.9.0] - 2026-08-31

### Added

- `scan` and `paired`, inverse period <-> date transforms. `scan(name, flows,
  opening, combine, query)` accumulates a period-keyed series into a
  date-keyed series: `opening` at the first period's start, then
  `combine(prior, flow)` at each period end, where `prior` is the series' own
  answer at the period start (lazy, memoized, cycle-friendly — a flow may read
  the scanned series at its own period start). `paired(name, balances, fn,
  query)` pairs consecutive dates of a date-keyed series into
  `Period(prev, curr)` cells valued `fn(begin, end)` (e.g.
  `map2_some(operator.sub)` for balance deltas). `combine`/`fn` receive
  resolved answers including miss sentinels, matching `map`/`map2`.
- `Cell(name, fn)` and `KeyedCell(name, fn)` wrap a public `fn` for one-off
  unkeyed and keyed bodies. `@Cell.define` / `@KeyedCell.define` bind the
  function as the cell so the body can close over that name. Subclass `Rule` /
  `KeyedRule` to override `compute` with extra state. Series cells are stored
  as `Cell` instances. The paper LBO example uses `Cell` for growth and exit
  multiple (replace `fn` between scenarios).
- `multiply_some(...)` for Na-propagating float products over a tuple of
  `Maybe[float]` values.
- `some(value)` widens `V` to `Maybe[V]` for type inference (runtime identity).
- `value_or(value, default)` unwraps a `Maybe`: the value if present, otherwise
  `default`.

### Changed

- Renamed `combine_values` to `combine_some` and `add_values` to `add_some` to
  match `map_some` / `map2_some`.

## [0.8.1] - 2026-08-18

### Changed

- Demand-cycle iteration no longer requires a seed on the runtime back-edge.
  A `seed`/`distance` spec on any executed demand in the cycle is enough from
  any query entrypoint, including through composed series (`+`, `map2`).
  Extra specs in the same cycle are additional residuals, not nested solvers:
  iteration continues until every seeded cell *observed this iteration* is
  within its own tolerance. Seeded demands that stop executing (a dropped
  sweep/trigger branch) are skipped, not treated as failure. Dependents are
  recomputed from the committed cut so cached values stay consistent. See
  `examples/iterative-solver/main.py`.

## [0.8.0] - 2026-08-13

### Added

- Added `last`, an as-of query that returns the latest cell at or before the
  query key (or `Na` if none), for balance-sheet-style point-in-time lookups.
- Added `covered`, a period query that sums cells that exactly tile the query
  period and returns `Na` on any gap or partial overlap.
- Added `PeriodExtendSeries` and `DateExtendSeries` for sequential
  composition: answer from a finite base until its domain is exhausted, then
  from a continuation built from the last base key. Period queries that cross
  the seam are split and folded with a required `combine`; date queries are
  dispatched to one side — the continuation owns dates at or after its first
  key, so an as-of (`last`) base query carries forward across any gap before
  the continuation's first cell. See `examples/extend-series/main.py`.
- Added `PeriodSeriesBase` and `DateSeriesBase` as the shared period/date
  series surface (`map`, `map2`, Na-aware arithmetic). Cell-backed
  `PeriodSeries` / `DateSeries` and derived combinators both inherit from
  these bases so operator chaining stays closed over the surface type.
- Added an iterative solver for demand cycles: `get` / `get_at` accept typed
  `seed` and `distance` used only when the demanded cell is already being
  computed. A cycle may mark every cyclic getter; only the back-edge is used
  as the cut, so the same cycle is solvable from either entry. `Context`
  iterates until successive guesses are close (`tol=1e-9`, `max_iter=1000`
  unless overridden), or raises `ConvergenceError`
  with the cut cell's seed and every iterate (and residuals) so oscillation
  or blow-up is visible. `abs_distance` and `maybe_abs_distance` cover `float` and `Maybe[float]`;
  other value types supply their own metric. See `examples/iterative-solver/main.py`.

### Changed

- Period/date map and operator combinators no longer subclass the cell-backed
  grid types; `isinstance` checks in arithmetic use the new base classes.
- Made every specialized period/date series class public. The concrete
  `PeriodMapSeries`, `PeriodMap2Series`, `DateMapSeries`, and `DateMap2Series`
  classes are now exported alongside their base, cell-backed, and extension
  counterparts.
- Moved `PeriodSeries` / `PeriodSeriesBase` into `orcaset.period_series` and
  `DateSeries` / `DateSeriesBase` into `orcaset.date_series`. Public imports
  for the existing classes from `orcaset` are unchanged.

## [0.7.1] - 2026-08-03

### Fixed

- Pin `astral-sh/setup-uv` to `v9.0.0` in the publish workflow so the
  tag-triggered PyPI job can resolve the action.

## [0.7.0] - 2026-08-03

### Added

- Publish tagged releases (`v*`) to PyPI via GitHub Actions using Trusted
  Publishing (OIDC).

### Changed

- Ship the `LICENSE` file in sdists and wheels via `license-files`.
- Install docs now point at the PyPI package (`uv add orcaset` /
  `pip install orcaset`) instead of a git URL.

## [0.6.0] - 2026-08-03

### Added

- Added `PeriodSeries` and `DateSeries` for the common `Q = K = Period` /
  `date` cases, with Na-propagating arithmetic (`+`, `-`, `*`, `/`, unary
  `+/-`), derived operator names, and `.named(...)` for display labels.
  Domain merges use `period_union` / `date_union` respectively.
- Added `date_union(...)` for lazily merging ascending date domains into a
  unique sorted spine, for composing date-keyed series.
- Added `exact_or(default)` and `accrual_or(yf, default)` as non-`Maybe`
  sisters of `exact` / `accrual` that substitute a default on miss.

## [0.5.0] - 2026-08-01

### Added

- Added the `Series.define(...)` decorator constructor for defining a `Series`
  directly from its value function.
- Added `MapNSeries` for answer-level composition of a nonempty tuple of
  homogeneous series, with a caller-supplied lazy domain merger.
- Added `period_union(...)` for lazily merging period domains and
  `combine_values(...)` and `add_values(...)` for Na-propagating value
  combination.
- Restored statement views for composing period- and date-keyed series and
  fixed-width, CSV, and Markdown table formatters for statement results.

### Changed

- Renamed `Series` to `BaseSeries` and `GridSeries` to `Series`.
- Changed demand resolution to use an explicit stack so deeply dependent rule
  chains do not exhaust Python's call stack.
- Renamed the recursive income example to `income.py`, added its quarterly
  statement output, and added a projection example with quarterly output.

## [0.4.0] - 2026-06-18

### Added

- Added `span.clip(...)` for defining span series clipped to an optional fixed
  start and end date.
- Added `span.map(...)` for defining span series by mapping each base span's
  period and value formula into a new formula.
- Added timeline-backed point helpers, including `point.from_list(...)`,
  `point.constant(...)`, `point.derived(...)`, `point.extend(...)`, point
  interpolation helpers, and `align_points(...)`.
- Added fluent `SpanSeriesDef` helpers for span transformations, including
  `.then(...)` for appending a continuation series clipped to the base series
  end date.
- Added lazy series refs for point and span convenience constructors, allowing
  constructors to accept zero-argument functions that return dependent series
  definitions.

### Changed

- Changed `span.extend(...)` continuation callables to receive the concrete
  base series end date instead of an optional date.
- Changed `PointSeriesDef` to use source point timelines plus an
  `interpolate(ctx, dt)` function for non-source query dates.
- Improved `Period` typing so `start` and `end` are typed attributes while
  preserving tuple unpacking.
- Improved `YF` singleton deepcopy typing to return `Self`.
- Changed Gauss-Seidel cell solving to prime newly resolving cells with `1.0`
  instead of `0.0` to avoid initial division by zero errors.

## [0.3.0] - 2026-06-01

### Added

- Added `Formula.sequence(...)` for collecting dynamic formula iterables into
  one formula.
- Added keyed span and point series collections for query-dependent dynamic rows,
  including statement expansion for period and date queries.

### Changed

- Replaced class-based `SpanSeries` and `PointSeries` APIs with immutable
  `SpanSeriesDef` and `PointSeriesDef` named tuple definitions. Series are now
  queried directly with explicit contexts, e.g. `revenue.value(ctx, period)` and
  `cash.query(ctx, dt)`.
- Renamed public series helper metadata from `name=` to `label=`.
- Updated examples and documentation to use def-object series.

### Removed

- Removed context-managed series instantiation via `Context.get(...)`.
- Removed `SpanSeriesFamily` and `PointSeriesFamily`; dynamic lines are now
  represented by creating ordinary series definition objects.

## [0.2.0] - 2026-05-21

### Added

- **Statement views** (`Stmt`, `Group`, `Total`, `LineRow`, `TotalRow`,
  `GroupRow`, `FamilyRow`, `FamilyLineRow`, `StatementResult`, `PeriodValue`,
  `DateValue`) for composing line items into structured, queryable financial
  statements. Statements support both period and date queries and resolve all
  referenced cells in a single call.
- **Series families** (`SpanSeriesFamily`, `PointSeriesFamily`,
  `SpanFamilyResult`, `PointFamilyResult`) for date-based dynamic series
  generation. Families create one ordinary series per key with caching owned
  by the `Context`, so families compose cleanly without leaking global state.
  Statements expand families by aligning keys across periods and reducing
  with the same aggregator used for regular span rows.
- **Output formatters** (`fixed_width_table`, `csv_table`, `markdown_table`,
  `DateFormatter`, `ValueFormatter`) for rendering `StatementResult` values.
  Formatters are period-aware and handle point boundary columns, totals,
  groups, and family rows.
- **Required `agg` on span series.** `SpanSeries` and span helpers now require
  an explicit aggregator (`sum_spans`, `avg_spans`, or a custom `SpanAgg`),
  threaded through scalar operators and span family value reduction. The
  `SpanAggregator` type alias and `SpanAgg` protocol are now public.
- **Series provenance and labels.** `Series` now supports an optional `label`
  attribute with `display_name` / `key_label` helpers so statements can render
  human-readable row names (with class-name fallback). Cells carry direct
  provenance back to the generating series; span/point queries, family
  binding, splitting, clipping, and cache materialization all preserve the
  most specific source. Dependency graph DOT output includes source labels
  when available.

### Changed

- **Module reorganization.** Span- and point-related series definitions moved
  from `series.py` into `span.py` and `point.py` respectively. `series.py`
  now contains only the shared `Series` base class. This removes a circular
  import between `series`, `span`, and `point` and eliminates the local
  imports previously needed to break the cycle.
- **Span aggregator functions are now descriptors,** which silences a type
  checker false positive when assigning `agg = sum_spans(0.0)` at class
  scope. No runtime behavior change.
- **README and quickstart example** rewritten to reflect the new statement
  view, formatter, and aggregator APIs, with a runnable end-to-end snippet.

### Fixed

- **Span cache convergence.** Clipped and gap-fill query spans are now stored
  in a separate `derived_spans` cache, while materialized source spans
  remain in `source_spans`. Derived spans are reused for exact lookups and
  excluded from source scans, fixing non-convergence caused by recreating
  clipped span cells during cell solving. Includes regression coverage.

[Unreleased]: https://github.com/orcaset/orcaset-py/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/orcaset/orcaset-py/compare/v0.8.1...v0.9.0
[0.8.1]: https://github.com/orcaset/orcaset-py/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/orcaset/orcaset-py/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/orcaset/orcaset-py/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/orcaset/orcaset-py/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/orcaset/orcaset-py/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/orcaset/orcaset-py/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/orcaset/orcaset-py/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/orcaset/orcaset-py/compare/v0.2.0...v0.3.0
