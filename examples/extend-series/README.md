# Extend Series

This example demonstrates horizontal series composition with `PeriodExtendSeries`: a finite historical series and a later forecast are laid end-to-end so one line item answers both sides of the seam.

## How It Works

`hist_revenue` is a finite quarterly base that uses `covered`, so it answers only when historical cells exactly tile the requested period. `revenue` appends a continuation that receives the last historical period and builds a monthly growth forecast from that period's end. Each piece keeps its own frequency and query behavior; `PeriodExtendSeries` is the join.

Queries that stay inside history never materialize the forecast. Queries after the last historical end use only the continuation. A query that crosses the seam is split, each side is evaluated with its own rules, and `combine` (`map2_some(operator.add)`) folds the two answers. A `Stmt` can therefore present historical and projected quarters as one continuous row.

## Run

From the repository root:

```sh
uv run python examples/extend-series/main.py
```

Running the script prints the output below.

```txt
Left of seam (historical quarters)
  Period(2025-01-01, 2025-04-01): 300.0000
  Period(2025-04-01, 2025-07-01): 330.0000
  Period(2025-07-01, 2025-10-01): 363.0000

Partial historical period stays Na (Period(2025-09-01, 2025-10-01)): Na

Right of seam (monthly projection, 1% growth off last-quarter run-rate)
  Period(2025-10-01, 2025-11-01): 122.3414
  Period(2025-11-01, 2025-12-01): 123.5648
  Period(2025-12-01, 2026-01-01): 124.8005

One composed row
Start                2025-01-01  2025-04-01  2025-07-01  2025-10-01
End      2025-01-01  2025-04-01  2025-07-01  2025-10-01  2026-01-01
revenue                  300.00      330.00      363.00      370.71
```

## Layout

| File | Role |
| --- | --- |
| [`main.py`](main.py) | Defines the historical base, appends a monthly forecast, and queries both sides of the seam. |
