# Series Composition

This example builds a small income statement from linked-list-backed `Series` values.

`Series.define` unfolds recursive monthly revenue cells. `ops.map_values` derives COGS,
and `ops.add(..., merge_keys=period_union)` aligns and adds line items:

```py
cogs = ops.map_values("cogs", revenue, fn=map_some(lambda value: value * -0.5))
gross_profit = ops.add("gross_profit", revenue, cogs, merge_keys=period_union)
income = ops.add("income", gross_profit, rd, sga, merge_keys=period_union)
```

The query function on each series remains responsible for arbitrary-period behavior;
this model uses `accrue(YF.cmonthly)`.

## Run

```sh
uv run python examples/series-composition/main.py
```

The script prints arbitrary-period queries and a quarterly `Stmt`.
