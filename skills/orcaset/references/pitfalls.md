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

`exact` only hits when the query key equals a cell key. Partial/overlapping
periods need `accrual(yf)`. Sourced historicals that must not be interpolated
use `covered` (sum of complete cells only). Dated balance lookups should stay
`exact` at `p.start` / `p.end`.

## History and forecast on one spine

Do not `map2` a coalesce of historicals and projections: a query that crosses
the cutoff will keep a partial historical answer and drop the forecast. Use
`PeriodExtendSeries` (flows) or `DateExtendSeries` (stocks). Do not seed
the first forecast period with a lookback that is finer than the historical
grid when historicals use `covered`.

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

Mutual `get_at` cycles raise `CycleError` at resolve time unless the demand
that closes the cycle provides a typed `seed` and `distance`:

```python
end = yield from get_at(debt, p.end, seed=0.0, distance=abs_distance)
```

`seed` and `distance` are checked against the fetched type (here `float` from
`exact_or`). They are ignored when the target is not already on the stack, so
they are not a default for missing keys. Prefer `exact_or` / `accrual_or` for
circular items that always exist, so `abs_distance` matches; `exact` answers
`Maybe[float]` and needs `maybe_abs_distance`. Custom types supply their own
metric. A cycle that does not settle raises `ConvergenceError`; inspect
`err.values` (seed then each iterate) and `err.residuals` to see oscillation
or blow-up.

Timing can still break a cycle without iteration (e.g. depreciation reads
*beginning* PPE, PPE update applies dep at period end). Use iteration when the
economics are simultaneous (average-balance interest, cash sweeps). Mark every
cyclic `get` / `get_at` with `seed`/`distance`: only the back-edge is cut, so
extra specs are unused for that evaluation order rather than nested solvers.

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
