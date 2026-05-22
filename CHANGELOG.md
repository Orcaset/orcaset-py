# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the version is `0.x`, the public API is considered experimental and may
change between minor releases.

## [Unreleased]

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

[Unreleased]: https://github.com/orcaset/orcaset-py/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/orcaset/orcaset-py/compare/v0.1.0...v0.2.0
