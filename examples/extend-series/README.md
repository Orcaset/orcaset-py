# Extend Series

This example extends a finite quarterly history with an infinite monthly forecast, horizontally building a single `revenue` series.

## How It Works

### The base chain

`hist_revenue` is a short series built from a list of quarterly historical revenue values. It is the base series which will be extended.

```py
HISTORICAL = [
    (Period(date(2025, 1, 1), date(2025, 4, 1)), 300.0),
    (Period(date(2025, 4, 1), date(2025, 7, 1)), 330.0),
    (Period(date(2025, 7, 1), date(2025, 10, 1)), 363.0),
]

accrue_monthly = accrue(YF.cmonthly)
hist_revenue = Series.of("hist_revenue", accrue_monthly, HISTORICAL)
```

### The forecast as a recursion on the chain

`grow` builds an infinite monthly chain directly from `Cons` nodes. Each node's value cell is `GROWTH` times the prior cell, and that same cell is threaded into the next tail, so no month has to query back through the composed series:

```py
def grow(period: Period, prior: Rule[float]) -> Cells[Period, float]:
    def node() -> Cons[Period, float]:
        def value() -> Effect[float]:
            return (yield from get(prior)) * GROWTH

        this = Cell(f"forecast_revenue@{period}", value)
        return Cons(period, this, grow(period.from_end(MONTHLY), this))

    return Cell(f"forecast_revenue.tail@{period}", node, structural=True)
```

Placing the recursive call inside a `Cell` in the tail slot is what keeps the chain lazy: the next node is built only when a walk demands it.

### Splicing at the frontier

`Series.extend` wraps each historical tail. When a wrapped tail is exhausted it hands the last historical node to `forecast_cells`, which reads the node's key to fix the first forecast month and the node's cell to seed the run-rate. The wrapper then resolves to the head of the forecast, so nothing past the seam is wrapped and no historical tail is forced ahead of the walk.

```py
revenue = Series.extend("revenue", accrue_monthly, base=hist_revenue.cells, cont=forecast_cells)
```

The composed series is governed by one query, `accrue_monthly`, so a query that cuts through a historical quarter is prorated and a query that spans the seam sums both sides.

## Run

From the repository root:

```sh
uv run python examples/extend-series/main.py
```

The output shows the original quarterly history, a prorated partial quarter, a 10% monthly forecast, one composed statement row, and its cross-seam dependencies.
