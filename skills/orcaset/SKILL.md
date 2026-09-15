---
name: orcaset
description: Build and modify financial statement models in Python with Orcaset, including linked operating schedules, balances, cash flows, scenarios, and statement reporting. Use when the model uses Orcaset or the user requests it.
---

# Financial modeling with Orcaset

Orcaset represents a model as a lazy, typed dependency graph. Keep assumptions and financial relationships in that graph; materialize numbers only for reporting and validation.

This guide uses the Orcaset 0.12 API. Inspect the installed exports and relevant signatures before adapting existing code: older releases used `PeriodSeries`, `Cell`, and `Step`; 0.12 uses `Series`, `Fn`/`Val`, and `Effect`. Use the project's installed version rather than upgrading it to fit an example.

## Build or modify a model

1. Identify the requested outputs, existing public nodes, source inputs, units, signs, and time boundaries. For edits, trace the affected relationships and preserve the surrounding model's conventions.
2. Separate interval flows (`Period`) from dated balances and events (`date`). A recurring monthly or annual amount is a `Period`-keyed series even when its values are constant; date-keyed observations cannot answer period queries. Anchor period boundaries to the model's transaction and fiscal dates — a year ending December 31 runs from the prior December 31, not January 1. Decide how each line answers exact, partial, combined, and missing queries. Read [graph-and-queries.md](references/graph-and-queries.md) when defining or composing series.
3. Put adjustable inputs in `Val` and retrieve them with `yield from get(input)`. Within computations, retrieve upstream model values with `yield from get_at(series, key)`. These effects give Orcaset its dependency tracking and scenario behavior. Use a `Context` outside computations to evaluate one run.
4. Use `ops` for same-key derived lines. Use lazy series construction when the domain or period-to-period relationship changes. Read [schedules.md](references/schedules.md) for historical/forecast joins, rollforwards, balance changes, cohorts, and circular formulas. Read [inputs-and-types.md](references/inputs-and-types.md) for scenarios, sourced values, and units.
5. Keep operating, investing, financing, and supporting schedules linked through named nodes. Define subtotals as formulas; `stmt.Total` displays a subtotal and its components but does not create the formula. For substantial projects, separate inputs/model definitions from reporting entrypoints in a way that fits the existing project.
6. Run the model and its configured type checker. Check representative source-to-output dependencies, boundary behavior, and economic reconciliations. Read [validation-and-reporting.md](references/validation-and-reporting.md) when checking or delivering a model.

## Core constraints

- Export queryable model nodes when callers need a reusable model; a table or cached dictionary is only a report.
- `Series[K, V, W]` distinguishes key type, stored value type, and query-answer type. Annotate custom helpers and generic aliases with Python's PEP 695 syntax; resolve type errors at the actual interface.
- Emit strictly ascending keys. Period keys must not overlap. Use the requested fiscal/transaction dates, preserving month-end offsets where appropriate.
- Missing (`Na`) is distinct from zero. Default only where absence has an explicit economic meaning; do not conceal missing required inputs.
- A context memoizes one run. After changing assumptions, use a fresh context.
- Unfold steps may compute values effectfully. Use a value `Thunk` when the chain node must exist before its value resolves, or when key discovery must avoid value evaluation. A bare callable is data, not deferred computation.
