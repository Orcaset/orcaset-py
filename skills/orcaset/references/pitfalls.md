# Orcaset pitfalls

## Closing over the loop variable

**Wrong:** `def factory(): ... get_at(series, k)` where `k` is the `for` loop variable — every factory may see the last `k`.

**Right:** `def factory(p: Period = k): ... get_at(series, p)` (default-arg capture).

## Forgetting `yield from`

`get_at` / `get` return generators. Use `value = yield from get_at(...)`. A bare `get_at(...)` without `yield from` does not resolve the dependency.

## Ignoring `Na`

Missing keys return `Na`. Use `isna(x)` before multiplying/adding, or use
`exact_or` / `accrual_or` only when absence has a defined default. Blind
arithmetic on `Na` propagates emptiness. Converting a required missing input to
zero can conceal a broken dependency or incomplete model.

## Wrong timeline anchor

Financial periods default to month-end boundaries. `Period.seq` preserves its
input anchor, so `date(2026, 1, 1)` with a monthly offset produces first-of-month
boundaries rather than financial month-ends. Use a month-end starting date and
`relativedelta(months=1, day=31)` unless explicitly directed otherwise.

Yield keys in ascending chronological order without unintended duplicates or
rollforward gaps. Do not sort potentially overlapping periods: `Period` uses a
partial order for overlaps.

## Wrong series kind for stocks vs flows

- Period flows (revenue, capex, net income for a period) → `PeriodSeries` + usually `accrual`.
- Point-in-time balances (cash, PPE, equity) → `DateSeries` + usually `exact`.
- Mixing these without an intentional rollforward (period → date) breaks the model.

## Accrual vs exact mismatch

`exact` only hits when the query key equals a cell key. Partial/overlapping periods need `accrual(yf)`. Dated balance lookups should stay `exact` at `p.start` / `p.end`.

## Aggregating ratios like flows

Margins, rates, prices, per-share measures, and averages are not ordinarily
additive. Summing monthly ratios through `accrual` does not produce a valid
quarterly ratio. Resolve and aggregate the numerator and denominator first,
then compute the reporting-period ratio.

## Ambiguous rate units

Applying an annual growth or interest rate once per month overstates the model.
Name rates by unit and document whether conversion uses compounding, simple
accrual, or a specified day-count convention.

## Cycles

Mutual `get_at` cycles raise `CycleError` at resolve time. Break cycles with timing (e.g. depreciation reads *beginning* PPE, PPE update applies dep at period end) or with exogenous inputs.

## Unsigned / double-negative expenses

Pick one sign convention and stick to it. If costs are stored negative, add them to revenue; if positive, subtract. Capex and depreciation in rollforwards are easy to flip twice — match `examples/simple-three-statement.py`.

## Generator returned as a cell value

A cell’s resolved value must not be a bare generator; factories return `float` (or other non-generator payloads). Wrap streamed data in the series/`Replayable` machinery instead of returning a generator from `compute`.

## Private / unstable APIs

Import from `orcaset` public `__all__`. Avoid reaching into underscored internals. The library is `0.x` and may rename constructors between minors — check `CHANGELOG.md` when upgrading.

## Evaluating with multiple Contexts by accident

Memoization and dependency traces live on one `Context`. Reuse the same `ctx`
for related `get_at` / `Stmt.values*` calls within one run. Create a new
`Context` after changing assumptions, source inputs, or scenario configuration;
otherwise memoized values may represent the prior run. Use a separate context
for each scenario.

## Suppressing type-checker findings

A model is incomplete while its configured type checker reports any error or
warning. Fix types at their source. Static type casts, `type: ignore` comments,
checker-specific suppression comments, and equivalent mechanisms are strictly
prohibited.
