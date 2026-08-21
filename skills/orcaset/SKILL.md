---
name: orcaset
description: >-
  Build, extend, debug, and validate financial models in Python with the
  orcaset library, including operating forecasts, three-statement models,
  valuation schedules, debt and interest schedules, working-capital models,
  cohort schedules, accruals, balance-sheet rollforwards, scenario models,
  statement presentation, and model reconciliation. Use when a task requires
  PeriodSeries, DateSeries, PeriodExtendSeries, DateExtendSeries, Period,
  Context, get/get_at effect handlers, accrual/covered/exact/last queries, or
  Stmt output.
---

# Orcaset

orcaset builds financial models as typed Python series resolved in a `Context`.
Dependencies come from `yield from get_at(...)` / `get(...)`, not spreadsheet
addresses.

API is experimental (`0.x`).

# Environment

- Requires Python >= 3.14
- All code should type check; prefer `pyrefly` but other checkers may work; warn the user if no type checker is available
- If `orcaset` is not already available, install it from PyPI with `uv add orcaset` (preferred) or `pip install orcaset`
- Prefer Python and project management with uv

## Mental model

1. **Keys**: flow items use `Period`; stocks use `date` if applicable to a single date or `Period` if applicable to a time span.
2. **Series**: `PeriodSeries` / `DateSeries` (or `Series`) hold named cells + a query (`accrual(...)` / `covered` / `exact`).
3. **Cells**: constants or `CellFactory` generators that `yield from get_at` / `get`.
4. **Compose**: arithmetic (`+`, `-`, `*`, `/`), `.named(...)` for labels, and
   `PeriodExtendSeries` / `DateExtendSeries` to compose a later regime onto a
   finite base.
5. **Evaluate**: `Context().get_at(series, key)` or `Stmt(...).values(ctx, periods)`.
6. **Format**: `fixed_width_table` / `csv_table` / `markdown_table`.

## Period convention

Interpret named financial periods as `(start, end)` tuples bounded by
month-end dates unless the user explicitly specifies another convention.

- `January 2027` -> `Period(date(2026, 12, 31), date(2027, 1, 31))`
- `Q4 1990` -> `Period(date(1990, 9, 30), date(1990, 12, 31))`
- `CY 2020` -> `Period(date(2019, 12, 31), date(2020, 12, 31))`

Treat an unqualified quarter or year as calendar-based. Do not infer a fiscal
calendar from `FY` or a company name; obtain the fiscal year-end from the user
or provided source material.

Build recurring month-end periods with a month-end-preserving offset:

```python
MODEL_START = date(2026, 12, 31)
MONTH = relativedelta(months=1, day=31)
january_2027 = next(Period.seq(MODEL_START, MONTH))
```

Use the same boundary convention for flows and dated balances: a flow for a
period runs from `p.start` to `p.end`, while beginning and ending balances are
looked up at those respective dates. `Period.seq` preserves the supplied
anchor; it does not reinterpret a first-of-month anchor as a financial
month-end.

## Quick start

```python
from datetime import date
from collections.abc import Iterator
from itertools import islice, repeat
from dateutil.relativedelta import relativedelta
from orcaset import (
    YF,
    Context,
    Period,
    PeriodSeries,
    Step,
    Stmt,
    Total,
    CellFactory,
    accrual,
    fixed_width_table,
    get_at,
    isna,
)

MODEL_START = date(2025, 12, 31)
MONTH = relativedelta(months=1, day=31)
ANNUAL_GROWTH = 0.10
accrue = accrual(YF.cmonthly)


@PeriodSeries.define("Revenue", accrue)
def revenue() -> Iterator[tuple[Period, float | CellFactory[float]]]:
    periods = Period.seq(MODEL_START, MONTH)
    yield next(periods), 100.0
    for k in periods:

        def factory(p: Period = k) -> Step[float]:
            prior = yield from get_at(revenue, p.shift(-MONTH))
            if isna(prior):
                raise ValueError(f"missing prior revenue for {p}")
            return prior * (1 + ANNUAL_GROWTH) ** YF.cmonthly(p.start, p.end)

        yield k, factory


costs = (revenue * -0.50).named("Costs")
profit = (revenue + costs).named("Profit")

ctx = Context()
periods = list(islice(Period.seq(MODEL_START, MONTH), 4))
stmt = Stmt(Total(profit, [revenue, costs]))
print(fixed_width_table(stmt.values_for_periods(ctx, periods)))
```

## Workflow checklist

When building or extending a model:

1. Fix timeline constants (`MODEL_START`, `relativedelta` step, day-count / `YF`).
2. Define assumptions as module-level numbers (growth, margins, initials).
3. Add flow line items as `PeriodSeries` (`accrual(...)` for overlapping queries).
4. Add stock items as `DateSeries` (`exact`) that roll from prior date + period flows.
5. Wire `Stmt` with `Group` / `Total` mirroring statement hierarchy.
6. Evaluate in one `Context`; print with a formatter; use `ctx.dependencies(series, key)` when debugging.
7. Evaluate a small representative horizon before expanding the model.
8. Assert model invariants rather than relying only on formatted output: balance-sheet checks, rollforwards, subtotals, required inputs, and reporting-period boundaries.
9. Inspect dependencies for at least one forecast period and one boundary period.
10. Run the repository's formatter, type checker, and tests after editing code.

A model is not complete until its configured type checker passes with no errors
or warnings. Fix the types at their source. Static type casts, use of `Any`,
`type: ignore` comments, checker-specific suppression comments, and equivalent
mechanisms are strictly prohibited.

## Series construction

| Need | Pattern |
|------|---------|
| Recursive / dependent series | `@PeriodSeries.define(name, query)` + factories |
| Constant each period | `PeriodSeries(name, lambda: zip(Period.seq(...), repeat(x)), query)` |
| Scalar-driven line | `(base * rate).named("...")` |
| Sum / difference | `(a + b).named("...")` or `(a - b).named("...")` |
| Sign flip | `(-series).named("...")` |
| Point-in-time balances | `DateSeries(name, cells_fn, exact)` (or `last` for as-of carry-forward) |
| Horizontal composition | `@PeriodExtendSeries.define(name, hist, combine)` (flows) or `@DateExtendSeries.define(name, hist)` (stocks) |
| Unkeyed input / derived scalar | `Cell(name, fn)` or `@Cell.define(name)`; subclass `Rule` for extra state |

**Closure rule:** capture the loop key with a default arg (`def factory(p: Period = k)`), never close over the loop variable alone.

## Effect handlers

Inside a factory / `compute`:

```python
prior = yield from get_at(other_series, key)  # keyed
keys = yield from get(series.keys())  # unkeyed Rule
end = yield from get_at(debt, as_of, seed=0.0, distance=abs_distance)  # cyclic
```

Always `yield from`. Treat missing data according to its economic meaning:

- Use `exact_or(0.0)` / `accrual_or(..., 0.0)` only when absence genuinely means zero.
- Use `isna(...)` and raise a descriptive error when an input is required.
- Use an explicit seed or opening balance for the first modeled period.
- Do not convert `Na` to zero merely to make a model run.

## Cyclic value dependencies

Cycles are supported. Mutual `get` / `get_at` calls raise `CycleError` unless
some demand in the cycle passes **both** `seed` and `distance`. They are typed
against the fetched value: `seed` is the initial guess, `distance` maps two
values to a residual. Put the spec on the economically unknown access (for
example ending debt from interest). One cut is enough from any query
entrypoint, including through composed series (`ebitda + interest`).

```python
end = yield from get_at(debt, p.end, seed=0.0, distance=abs_distance)
```

- `abs_distance` for `float` (`exact_or` / `accrual_or`); `maybe_abs_distance`
  for `Maybe[float]` (`exact` / `accrual(...)` / `last`); custom types supply their
  own metric.
- Extra specs in the same cycle are extra residuals, not nested solvers.
  Iteration continues until every seeded cell observed this iteration is
  within its own tolerance. A seeded demand that stops executing (dropped
  sweep/trigger) is skipped, not treated as failure.
- They are ignored when the demand is not part of a cycle — not a default
  for missing keys.

Use iteration when the economics are simultaneous (average-balance interest,
cash sweeps). *Prefer timing* when a cycle can be broken (e.g. depreciation
reads *beginning* PPE).

## Inspecting dependencies

`Context` records the `get` / `get_at` graph for the current run. Reuse the
same `ctx` used to evaluate the model. Inspect the dependency graph to confirm
or debug model results.

```python
tree = ctx.dependencies(series, key)  # keyed series
print(tree)  # indented name@key = value tree
print(tree.value, tree.deps)

print(ctx.rule_dependencies(series.keys()))  # unkeyed Rule
```

`dependencies` / `rule_dependencies` resolve first, then return a `DepNode`
(`name`, `key`, `value`, `deps`). Use after a surprising value. Inspect at
least one ordinary forecast period and one historical/forecast or frequency
boundary.

## Queries

- `accrual(yf)` — weight overlapping cells by year-fraction (`YF.cmonthly`, `YF.act360`, or a custom `(d1, d2) -> float`).
- `covered` — sum cells that exactly tile the query period; `Na` on any gap or partial overlap (typical for sourced historicals).
- `exact` — require an exact key match (typical for dated balances and cohort schedules).
- `last` — latest cell at or before the query key, or `Na` (as-of lookups that should carry a balance forward).
- `accrual_or(yf, default)` / `exact_or(default)` — substitute a default on miss instead of `Na`.

Do not model ratios, rates, prices, or per-share measures as additive flows and
then aggregate them with `accrual(...)`. Derive reporting-period ratios from the
reporting-period numerator and denominator, and document the intended
aggregation for averages and other non-additive metrics.

## Statements

- `Total(series, [children...])` — total line with indented children.
- `Group([items...])` — section without its own total series.
- `Stmt(*sections)` — one or more top-level groups/totals (e.g. IS + CF + BS).
- Period models: `values_for_periods(ctx, periods)` or `values(ctx, periods)`.
- Mixed period/date statements: `values(ctx, periods)` answers date series at period boundaries.

## Additional resources

- API summary: [references/api.md](references/api.md)
- Statement and series patterns: [references/patterns.md](references/patterns.md)
- Common mistakes: [references/pitfalls.md](references/pitfalls.md)
