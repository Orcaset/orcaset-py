# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the version is `0.x`, the public API is considered experimental and may
change between minor releases.

## [Unreleased]

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

[Unreleased]: https://github.com/orcaset/orcaset-py/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/orcaset/orcaset-py/compare/v0.2.0...v0.3.0
