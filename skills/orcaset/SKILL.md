---
name: orcaset
description: "Build, extend, inspect, debug, and validate typed financial models with Orcaset's lazy Series, Rule, Cell, and effectful cell-chain APIs. Use for Orcaset model graphs, unfold/extend/merge operations, period or date queries, historical/forecast schedules, rollforwards, cohorts, circular calculations, scenarios, dependency tracing, or materializing Orcaset values. Do not use for ordinary Python calculations that do not need an Orcaset dependency graph."
---

# Orcaset

Orcaset models are lazy, typed dependency graphs. A `Series` combines an effectful chain of keyed cells with a query function; a `Context` resolves and memoizes rules for one run.

## Invariants

- Keep queryable outputs as `Rule`, `KeyedRule`, `Cell`, or `Series` objects. Do not replace model nodes with calculated containers or hide a private `Context` behind an export.
- Inside a rule, unfold step, query, or thunk, retrieve dependencies only with `yield from get(...)` or `yield from get_at(...)`. Do not add a second cache or use local running values in place of graph edges.
- Treat a series' structure and values separately. `Series.cells` is a lazy `Cells[K, V]` cons chain; walking tails discovers keys, while demanding a node's `cell` resolves its value.
- Wrap deferred cell computation in `Thunk`. Every non-`Thunk` unfold value, including a callable, is stored as data. A live generator is invalid as a cell value.
- Emit keys in strictly ascending order. For `Period`, ordering means entirely before, so overlapping periods are not generally sortable.
- Choose the key type, query policy, and missing-value policy explicitly. Preserve `Na` unless absence has a clear economic meaning such as zero.
- Use `Cell` for an assumption that must vary between fresh contexts. Keep a fixed scalar plain when adjustability is not part of the model contract.
- Build same-key derived values with `ops.map_values`, `ops.map2`, or the arithmetic operations. Transform chains directly only when the result needs structural state, a new domain, a continuation, or nested series.
- Use Python 3.14+ and PEP 695 syntax. Finished code must pass the configured type checker without `Any`, casts, ignores, or suppression workarounds.

## Workflow

1. Inspect the installed Orcaset version, public exports, changelog, and local conventions; the API is experimental.
2. Define each public node's key type, cell-value type, query-answer type, domain, miss behavior, and adjustable inputs.
3. Sketch both value dependencies and structural dependencies. Mark every upstream read that must become `get` or `get_at`.
4. Choose `Series.of` for finite literal pairs, `Series.unfold` or `@Series.define` for lazy/stateful domains, and `Series.extend` for horizontal composition.
5. Compose answer-level calculations with `ops`; use `map_cells`, `scan_cells`, or `merge_cells` only for genuine chain transformations.
6. Query every public export directly in a fresh `Context`. Exercise ordinary, missing, partial, boundary, continuation, and cyclic cases as applicable.
7. For statement output, compose `Stmt`, `Total`, and `Group`, then render with `fixed_width_table`, `markdown_table`, or `csv_table`. Inspect dependency trees, then run static checking, tests, and economic reconciliations.

## References

Read only what the task needs:

- Always read [modeling-core.md](references/modeling-core.md) when creating or changing a graph or series.
- Read [queries-and-missing-values.md](references/queries-and-missing-values.md) for timelines, query functions, partial periods, and `Na` policies.
- Read [rollforwards-and-cycles.md](references/rollforwards-and-cycles.md) for balances, flow-to-stock conversion, debt, cash, sweeps, or circular formulas.
- Read [cohort-schedules.md](references/cohort-schedules.md) for depreciation, amortization, vintages, waterfalls, or nested schedules.
- Read [assumptions-and-value-types.md](references/assumptions-and-value-types.md) for scenarios, sensitivities, units, citations, or other rich values.
- Read [runtime-and-debugging.md](references/runtime-and-debugging.md) when evaluating, walking keys, tracing dependencies, or debugging laziness.
- Read [project-quality.md](references/project-quality.md) when organizing a project or completing validation and handoff.

## Completion gate

Before finishing, confirm that public outputs remain Orcaset nodes; keys are strictly ascending; deferred values use `Thunk`; dependencies are effectful; query, miss, and boundary behavior is intentional; traces show the expected economic graph; and static checking plus tests pass.
