# Rollforwards and cycles

## Flow-to-stock rollforwards

A stock is normally a `DateSeries`; the movements that change it are
`PeriodSeries` flows. The opening stock is keyed at the first period's start,
and each ending stock is keyed at that period's end.

Prefer `scan` when its shape fits:

```python
balance = scan(
    "Cash balance",
    net_cash_flow,
    opening_cash,
    map2_some(operator.add),
    last,
)
```

`scan` reads the scanned series at the period start and the flow over the
period through Orcaset effects. It remains lazy, memoized, and compatible with
cycles. `paired` is the inverse shape: it maps consecutive dated balances to
period cells, such as a balance change.

For a custom rollforward, discover the flow domain with `yield from
get(flows.keys())`; each ending cell must retrieve the prior balance and
current flows with `get_at`. Do not accumulate a Python variable while
building cells.

Keep all cash flows and balances connected. For example, debt draws and
repayments should compose into a debt-flow series, which rolls into a single
debt-balance series. Do not create unrelated beginning- and ending-debt tables.
Choose the sign convention once and keep it on the exported movement: a draw
is normally positive and a repayment or sweep negative. Feed that same signed
movement into the rollforward; do not export a positive repayment and negate
it only inside `scan`.

## Keep financing domains compatible

Use one explicit key convention at each layer:

- Draws, purchases, exits, balloon payments, and other events on a particular
  day are `DateSeries` values keyed by `date`.
- Interest, free cash flow, and sweeps earned or paid over a period are
  `PeriodSeries` values keyed by `Period`.
- A balance is a `DateSeries`; query beginning and ending balances with
  `get_at(balance, period.start)` and `get_at(balance, period.end)`.

Never add or compare a date-keyed series to a period-keyed series. Either use
`scan` to roll period movements into a dated balance, or explicitly convert a
period movement to a date event keyed at `period.end` before composing it with
other dated events. Keep the requested period-flow export as a `PeriodSeries`
even if a dated adapter feeds the balance.

Balances that should carry between roll dates use `last`; `exact` makes an
otherwise valid between-date balance query return `Na`. An event cash-flow
line such as draws, repayments, purchases, or exit proceeds normally uses
`exact_or(0.0)`: no event on a reporting date is a valid zero, not an unknown.
Use `exact` only when the series represents event detail whose absence should
remain undefined. Test the opening date, every period start/end, a between-roll
date, and the payoff date.

The public balance at a settlement date must be post-settlement when the
settlement occurs on that date. If interest needs the pre-balloon ending debt,
model one pre-settlement balance for the cycle, then compose the dated balloon
movement into the public balance at the payoff date. Do not postpone the zero
balance to a synthetic following day. A pre-settlement helper is not a second
"beginning debt" table; beginning debt remains an as-of query on the same
rollforward.

## Genuine simultaneous dependencies

If a formula depends on its own simultaneously determined result—such as
interest on average beginning and ending debt—model the cycle directly. Put a
typed `seed` and `distance` on at least one economically unknown demand in the
cycle:

```python
ending = yield from get_at(
    debt,
    period.end,
    seed=0.0,
    distance=abs_distance,
)
interest_amount = rate * 0.5 * (beginning + ending)
```

One executed seed/distance specification anywhere in the cycle is enough from
any query entrypoint. It is a solver cut, not a default for missing values.

- Use `abs_distance` when the demanded type is `float`, commonly from
  `exact_or` or `accrual_or`.
- Use `maybe_abs_distance` when the demanded type is `Maybe[float]`, commonly
  from `exact`, `last`, or `accrual`.
- Rich value types require a seed of that type and a matching distance
  function.

Prefer timing instead of iteration when the economics are not simultaneous:
for example, depreciation may read beginning PPE and the period-end PPE update
may then apply depreciation. Use iteration for genuine average-balance,
sweep, or other same-period feedback.

## Diagnose failures

An unseeded demand cycle raises `CycleError`; inspect its path and locate the
economically unknown edge. A non-converging seeded cycle raises
`ConvergenceError`; inspect `values`, `residuals`, `seeded_residuals`, and
`unobserved` for oscillation, divergence, or conditional branches that stop
executing. Do not replace a failed cycle with hard-coded or closed-form output
unless the requested economics explicitly call for that formulation.

## Reconcile

Test each ending balance against opening balance plus movements. For financing
models also reconcile draws, repayments, balloon/exit settlement, and the
resulting equity cash flows. Query both the stock series and the upstream flow
series in the same context, then inspect dependencies at an ordinary period
and at the payoff or boundary date.
