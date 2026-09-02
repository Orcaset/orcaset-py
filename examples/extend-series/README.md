# Extend Series

This example lays a finite quarterly history and an infinite monthly forecast end to end.

`hist_revenue` is built with `Series.of`. `extend_period_series` appends a continuation
when a walk reaches the history frontier while retaining both query policies:

```py
revenue = extend_period_series(
    "revenue",
    hist_revenue,
    forecast_series,
    lambda left, right: add_some((left, right)),
)
```

The continuation receives the final historical key and returns a series. Historical
queries use `covered`, forecast queries use `accrual`, and cross-seam queries are split
and combined. A historical query that cuts through a cell remains `Na`, while a partial
forecast query accrues its share.

## Run

```sh
uv run python examples/extend-series/main.py
```
