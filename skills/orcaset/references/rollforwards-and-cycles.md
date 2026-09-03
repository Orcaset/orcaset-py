# Rollforwards and cycles

## Flow-to-stock rollforwards

Keep interval flows on `Period` keys and point-in-time balances on `date` keys. Convert each period movement to a dated event—normally at `period.end`—before combining it with other dated events. Preserve the original period-flow export when callers need it.

The new core has no specialized date/period series or value-level `scan`. Build a dated balance by structurally scanning a dated flow chain. Carry only the prior key as structural state; each balance value must demand the prior public balance and current flow:

```python
def cumulate[V](
    name: str,
    flows: Series[date, V, Maybe[float]],
) -> Series[date, Maybe[float], Maybe[float]]:
    def step(
        previous: date | None,
        day: date,
        _flow_cell: Rule[V],
    ) -> tuple[Thunk[Maybe[float]], date]:
        def value() -> Effect[Maybe[float]]:
            prior = 0.0 if previous is None else (yield from get_at(balance, previous))
            flow = yield from get_at(flows, day)
            if isna(prior):
                return flow
            return prior + value_or(flow, 0.0)

        return Thunk(value), day

    balance = Series(name, scan_cells(name, flows.cells, seed=None, fn=step), last)
    return balance
```

This remains lazy, memoized, traceable, and compatible with demand cycles. Do not carry a resolved balance in `scan_cells`' accumulator; that would make values depend on structural traversal rather than graph demands.

Choose one sign convention and retain it on exported movements. A draw is normally positive and repayment negative. Combine all dated movements with `ops.add(..., merge_keys=date_union, fill=0.0)`, then roll that single flow series into the balance. Include an explicit opening event or incorporate an opening `Cell` at the first key when the opening amount must be adjustable.

## Keep timing explicit

Interest and operating cash flow earned over an interval remain `Period`-keyed. Draws, purchases, repayments, and exit proceeds occurring on a day are `date`-keyed. A balance is date-keyed and queried at `period.start` and `period.end`.

Do not combine date and period series directly. For a finite period schedule, a dated adapter can use `Series.of` with `(period.end, Thunk(...))` pairs. For a lazy schedule, unfold the periods into ending-date keys and have each thunk query the original flow at that period.

Balances that carry between events use `last`; event flows where no event means zero normally use `exact_or(0.0)`. The public balance on a settlement date should be post-settlement. If a circular formula needs a pre-settlement balance, model a clearly named helper and then add the settlement event into the public balance on the same date.

## Genuine simultaneous dependencies

If a formula depends on its own simultaneously determined result—such as interest on average beginning and ending debt—model the cycle directly. Put a typed `seed` and `distance` on at least one economically unknown demand:

```python
ending = yield from get_at(
    debt_before_balloon,
    period.end,
    seed=0.0,
    distance=abs_distance,
)
interest_amount = rate * 0.5 * (beginning + ending)
```

One executed seed/distance specification anywhere in the cycle is sufficient from any query entrypoint. It is a solver cut, not a missing-value default.

- Use `abs_distance` for `float` answers.
- Use `maybe_abs_distance` for `Maybe[float]` answers.
- Rich value types need a seed of that type and a matching distance function.
- Extra specs are additional residual checks, not nested solvers.

Prefer timing over iteration when the economics are sequential—for example, depreciation can read beginning PPE before the period-end PPE update. Use a cycle for genuinely simultaneous average-balance, sweep, or trigger logic.

An unseeded cycle raises `CycleError`; inspect its path. A non-converging cycle raises `ConvergenceError`; inspect `values`, `residuals`, `seeded_residuals`, and `unobserved` for oscillation, divergence, or conditional demands that stop executing. Do not replace a failed cycle with hard-coded output merely to make it run.

## Reconcile

For every balance, test opening value plus signed movements equals ending value. Probe the opening date, ordinary period starts and ends, between-event dates, and settlement dates. For financing, also reconcile draws, sweeps, balloon payments, exit proceeds, and resulting equity cash flows. Inspect the dependency tree for an ordinary rollforward cell and for a cyclic or boundary cell.
