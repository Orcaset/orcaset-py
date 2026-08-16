# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the version is `0.x`, the public API is considered experimental and may
change between minor releases.

## [Unreleased]

### Added

- Added `examples/citations/`, a walkthrough that wraps a SpaceX 10-Q revenue
  fact as a `CitedFloat` subclass, grows it at 10% per quarter, and shows the
  EDGAR accession, frame, and companyconcept URL via printouts and
  `ctx.dependencies(...)`.

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
  the continuation's first cell. See `examples/projection.py`.
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
  other value types supply their own metric. See `examples/circular.py`.

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

[Unreleased]: https://github.com/orcaset/orcaset-py/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/orcaset/orcaset-py/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/orcaset/orcaset-py/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/orcaset/orcaset-py/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/orcaset/orcaset-py/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/orcaset/orcaset-py/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/orcaset/orcaset-py/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/orcaset/orcaset-py/compare/v0.2.0...v0.3.0
