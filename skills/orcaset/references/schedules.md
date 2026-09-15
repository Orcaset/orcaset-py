# Linked schedules

## Actuals and forecasts

Use `Series.flatten` to join successive segments while retaining each segment's query policy, such as non-interpolating actuals and interpolating forecasts:

```python
segments = Series.of("Segments", query.exact, [(0, actuals), (1, forecast)])
combined = Series.flatten(
    "Actuals and forecast", segments.cells,
    query=query.covered, split_keys=period_split,
)
```

`period_split` comes from `orcaset`. The outer integer keys specify segment order. A query inside a segment delegates unchanged; a crossing query splits at seams and folds the segment answers using the outer query. `query.covered` here sums pieces, preserving missing answers. Earlier segments own overlaps through their last key. Empty segments are skipped; gaps are governed by the next segment's query policy.

`continue_series(name, base, cont)` supplies a lazy component chain for `flatten`. `cont(last_node)` receives the last raw `Cons` or `None` and returns the next series. It runs only after base exhaustion; an infinite base never reaches its continuation. Start from `last_node.key`, and obtain the prior amount effectfully. Normalize a quarterly or annual historical amount to the forecast interval before applying growth when frequencies differ.

`Series.extend(name, query_fn, base=base.cells, cont=callback)` instead appends raw cells under a single query policy. Its callback returns a chain. Use this only when one query policy should govern both segments.

When a continuation value queries the combined series, a `Thunk` may be needed so the continuation node is available before seam traversal asks for its value. Inspect structural cycles separately from economic ones.

## Balances and movements

Keep cash, debt, working capital, and asset balances on dates. Keep interval earnings, interest, and cash flows on periods. Link a period's flow to its opening and closing balance via `p.start` and `p.end`. An event posted at settlement is date-keyed; use an adapter when combining period flows with dated events. A public balance must still answer between observations — use `query.last` (carrying the latest observation forward) rather than `query.exact`, which returns `Na` off the spine.

Cash-flow lines queried at transaction dates — purchase price, draws, repayments, exit proceeds, levered cash flow — are date-keyed events with `query.exact_or(0.0)` for dates with no event. Convert a period flow into a dated payment by posting it at `period.end` through a small adapter series, then combine dated flows with `ops.add(..., merge_keys=date_union, fill=0.0)`; a balance is the cumulation of its dated flows under `query.last`. Do not key a line on `Period` when its natural queries are dates — the key types will not compare.

For a rollforward, create the opening observation and then closing-date cells. Each closing value demands the prior public balance and the signed movements. Avoid a Python running balance or a resolved-value scan: those obscure the economic dependency and scenario recalculation.

For irregular dates, `scan_cells(name, source.cells, seed=..., fn=...)` can carry the previous date as structural state. The callback returns `(mapped_value_or_thunk, next_state)`; the value thunk reads the prior balance through `get_at` and the current flow through `get_at`.

For changes between consecutive balance observations, use a lazy unfold over the balance chain carrying the previous node/key. Emit `Period(previous_date, current_date)` and compute `ending - beginning` through demands of the balance at both endpoints. Do not treat the first observation as a change without a defined opening balance. A step-function balance supports arbitrary interval changes by querying its endpoints in a custom query; accrual of observed deltas would instead interpolate jumps, and `query.covered` or `query.exact` returns `Na` for off-grid intervals. `Series.of` accepts a query function `(key, cells) -> Effect` in place of a built-in policy:

```python
def balance_change(q: Period, _cells) -> Effect[Maybe[float]]:
    begin = yield from get_at(balance, q.start)
    end = yield from get_at(balance, q.end)
    if isna(begin) or isna(end):
        return Na
    return end - begin

change_in_balance = Series.of("Change in balance", balance_change, observed_delta_cells)
```

Choose based on the requested timing semantics.

Keep flows signed as the economics state: draws and proceeds are positive, sweeps and repayments negative, and a balance accumulates its signed movements (`beginning + sweep`), never magnitudes. An event series asked at dates with no event should answer zero (`query.exact_or(0.0)`) rather than `Na` when absence means "no event occurred."

An opening amount plus signed movements must equal the ending balance. Distinguish working-capital change from its cash-flow effect, and expense from cash payment. A public debt balance on maturity/settlement should reflect repayment; model any pre-settlement view as a keyed function derived from the balance and its flows (for example a `KeyedFn` returning beginning plus sweep on demand), not a second stored balance series.

## Circular calculations

For simultaneous economics such as average-balance interest, retain the cycle and attach a solver specification to an unknown demand:

```python
end = yield from get_at(debt, p.end, seed=0.0, distance=maybe_abs_distance)
```

Use `abs_distance` for `float` query answers and `maybe_abs_distance` for `Maybe[float]`, imported from `orcaset`. Rich answers need their own correctly typed seed and distance. One executed seed/distance specification in the cycle suffices from any entrypoint. A seed is not a missing-input default. Do not resolve the circularity with a manual fixed-point loop inside a `Thunk`; demand the unknown value with `seed`/`distance` so Orcaset's solver sees and solves the actual cycle.

Numerical cycles and chain-construction cycles differ. If a value needs a chain node still being constructed, return a `Thunk` to separate node availability from value resolution. Inspect `.tail` cycles for this issue; adding numerical seeds to structural demands is not a substitute.

`CycleError` identifies an unseeded dependency cycle. `ConvergenceError` can reflect divergence, oscillation, or conditional branches; inspect residuals and the economic equations. Use sequential timing when the economics are sequential, and test genuine cycles from multiple public entrypoints in fresh contexts.

## Cohorts and vintages

For depreciation, amortization, or other vintage schedules, let a source key create a child series whose domain follows the requested start, life, and timing conventions. Child values demand the originating source amount. If callers need nested schedules, expose a series of child series, for example:

```python
type Cohort = Series[Period, float, Maybe[float]]
cohorts = Series(
    "Cohorts",
    map_cells("Cohorts", capex.cells, lambda key, _cell: build_cohort(key)),
    query.exact,
)
```

`build_cohort` uses the key for structure; an effectful child step or deferred value reads `get_at(capex, key)` for the amount. Creating or walking cohort keys need not force source values.

An aggregate walks only eligible cohort nodes, demands each child, and queries it at the reporting key. Stop when ascending keys prove later cohorts irrelevant. Distinguish no active cohort (normally zero) from missing required source data. The aggregate's domain spans the reporting horizon, not just periods with active cohorts: start it at the horizon's first period and let the fold yield `0.0` when nothing is active, or callers querying early periods get `Na`. Use an independent reporting spine if reports include periods before the first cohort. Keep child query semantics and total interpolation semantics deliberate: a detail schedule is exact-keyed over its own life — periods outside it answer `Na`, not zero or an interpolated share — even when the aggregate interpolates partial periods.
