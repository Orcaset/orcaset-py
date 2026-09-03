# Extend Series

This example lays a finite quarterly history and an infinite monthly forecast end to end.

`hist_revenue` is built with `Series.of`. `Series.extend` appends a continuation when a
walk reaches the history frontier:

```py
revenue = Series.extend(
    "revenue",
    covered,
    base=hist_revenue.cells,
    cont=forecast_cells,
)
```

The continuation receives the final historical key and returns a linked cell chain.
Using `covered` for the composed query means aligned historical, forecast, and
cross-seam periods sum cleanly, while a query that cuts through a cell returns `Na`.

## Run

```sh
uv run python examples/extend-series/main.py
```
