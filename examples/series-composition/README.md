# Series Composition

This example builds a small income statement from linked-list-backed `Series` values.

`Series.define` unfolds recursive monthly revenue cells. `ops.map_values` derives COGS,
and `ops.period.add(...)` aligns and adds line items:

```py
cogs = ops.map_values("cogs", revenue, fn=map_some(lambda value: value * -0.5))
gross_profit = ops.period.add("gross_profit", revenue, cogs)
income = ops.period.add("income", gross_profit, rd, sga)
```

The query function on each series remains responsible for arbitrary-period behavior;
this model uses `accrual(YF.cmonthly)`. The common `PeriodFlow` alias keeps numeric
series annotations compact.

## Run

```sh
uv run python examples/series-composition/main.py
```

The script prints arbitrary-period queries and a quarterly `Stmt`.
