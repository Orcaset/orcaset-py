---
name: orcaset
description: "Build, extend, inspect, debug, and validate typed financial models with the Orcaset Python library. Use for tasks involving Orcaset rules, Cell inputs, PeriodSeries or DateSeries models, historical/forecast extensions, rollforwards, cohort schedules, circular calculations, dependency tracing, model statements, or materializing Orcaset values. Do not use for ordinary Python calculations that do not need an Orcaset model graph."
---

# Orcaset

Orcaset models are lazy, typed dependency graphs. Model values are rules or series resolved by a `Context`; they are not precomputed Python tables.

## Invariants

- Keep queryable model outputs as Orcaset `Cell`, `PeriodSeries`, `DateSeries`, or other `BaseSeries` objects. Do not replace them with `dict`, `list`, tuple dataframe, cached function, or `Replayable` exports.
- Inside a rule, factory, query, or cell-stream dependency, retrieve values only with `yield from get(...)` or `yield from get_at(...)`. This is how the context records dependencies and memoizes each rule/key. Do not add manual caches or compute recurrences with local running state.
- Use `Cell` for every assumption or scalar input that must change between scenarios or sensitivity runs without rebuilding the model graph. Demand it with `get`; use a new `Context` after changing its function. Decide that adjustability contract explicitly: a scalar fixed by the specification is a plain constant, not automatically a `Cell`.
- Decide the key type, query rule, and missing-value policy for every series. Preserve `Na` unless absence has a clear economic meaning of zero or another default value.
- Keep flows on `Period` keys and point-in-time balances on `date` keys unless the requested economics require another explicit design.
- Model connected economics through series composition. Do not hard-code derived outputs, duplicate upstream formulas cell by cell, or eagerly materialize child models at import time.
- When a derived line is a same-query scalar transform or combination of existing series, define it with series arithmetic, `map`, or `map2`; do not create another cell stream that repeats the formula at every key. Do not invent scalar adjustability when it would force an unnecessary cell stream, or invent a dependency merely to borrow another series' domain.
- Use Python 3.14+ and PEP 695 syntax. A finished project MUST pass its type checker, preferably Pyrefly, without casts, `Any`, ignores, unknown types, suppression comments, or similar workarounds.

## Workflow

1. Inspect the installed Orcaset version and existing project conventions.
2. Identify required exports, their exact public key domains, value types, query behavior, and which inputs must remain adjustable.
3. Sketch the dependency graph before writing formulas. Mark every dependency edge that will be a `get` or `get_at` demand.
4. Build native Orcaset nodes and compose derived lines from their upstream series. Keep evaluation and reporting separate from model definition.
5. Query every public export directly with its promised key type. Materialize representative ordinary, missing, partial, boundary, and cyclic cases in fresh contexts; trace surprising answers before changing formulas.
6. Run formatting, the configured type checker, tests, and economic reconciliations. Fix causes rather than suppressing findings.

## References

Read only the references needed for the task:

- Always read [modeling-core.md](references/modeling-core.md) when creating or changing a model graph.
- Read [queries-and-missing-values.md](references/queries-and-missing-values.md) when choosing timelines, queries, partial-period behavior, or `Na` versus a default.
- Read [rollforwards-and-cycles.md](references/rollforwards-and-cycles.md) for balances, debt, cash, PPE, retained earnings, sweeps, or circular formulas.
- Read [cohort-schedules.md](references/cohort-schedules.md) for depreciation, amortization, vintages, waterfalls, or nested schedules by source item.
- Read [assumptions-and-value-types.md](references/assumptions-and-value-types.md) for sensitivities, scenarios, units, citations, or other rich value types.
- Read [runtime-and-debugging.md](references/runtime-and-debugging.md) when evaluating, materializing, presenting, tracing, or debugging a model.
- Read [project-quality.md](references/project-quality.md) when organizing a project or completing validation and handoff.

## Completion gate

Before finishing, confirm that required exports remain Orcaset nodes, dependent values are demanded through effects, adjustable inputs are `Cell`s, misses and boundaries behave intentionally, dependency traces show the expected graph, and static checking plus model tests pass cleanly.
