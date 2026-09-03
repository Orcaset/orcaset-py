# Series Composition

This example uses a small income model to demonstrate arithmetic composition with series and scalar combinators from `orcaset.ops`.

```py
from orcaset import ops

cogs = ops.scale("COGS", revenue, -0.5)
gross_profit = ops.add("Gross Profit", revenue, cogs, merge_keys=period_union)
income = ops.add("Income", gross_profit, rd, sga, merge_keys=period_union)
```

Arithmetic lives under `ops` by convention. Keeping it explicit gives every result a name and makes the domain-merging policy visible without restricting the generic `Series` type to numeric values.

## How It Works

Orcaset's arithmetic helpers are conveniences built from more general series combinators:

- `ops.add` and `ops.mul` use `ops.combine` with `ops.filled` to combine any number of series.
- `ops.sub` and `ops.div` use `ops.map2` with `ops.filled` to combine two series.
- `ops.neg` and `ops.scale` use `ops.map_values` to transform one series with a scalar operation.

The series combinators lazily merge the source domains. Because this example is keyed by `Period`, it passes `period_union` as `merge_keys`; date-keyed series would normally use `date_union`. At each resulting key, and for arbitrary off-spine queries, the combinator queries every source at the same key. Each source therefore retains its own query semantics. Here, `accrue(YF.cmonthly)` controls how monthly values answer a query over another period.

The scalar helpers preserve the source domain and query behavior. For example, `ops.scale` is the arithmetic convenience for mapping a multiplication over every available value:

```py
from orcaset import map_some

cogs = ops.scale("COGS", revenue, -0.5)

# The underlying operation, written directly:
cogs = ops.map_values(
    "COGS",
    revenue,
    fn=map_some(lambda value: value * -0.5),
)
```

Arithmetic propagates `Na` by default. If any source answers `Na`, `add`, `mul`, `sub`, and `div` return `Na`; `neg` and `scale` use `map_some`, which leaves `Na` unchanged. The series-to-series helpers also accept an explicit `fill` value when missing answers should be substituted instead:

```py
total = ops.add("Total", actual, forecast, merge_keys=period_union, fill=0.0)
```

`ops.combine`, `ops.map2`, and `ops.map_values` remain available when a model needs a custom operation rather than one of these arithmetic conveniences.

## Run

From the repository root:

```sh
uv run python examples/series-composition/main.py
```

Running the script prints the outputs below.

```txt
Query line items over arbitrary periods:
  Revenue @ Period(2027-03-01, 2027-05-15):         283.94
  COGS @ Period(2027-03-01, 2027-05-15):           -141.97
----------------------------------------------------------
Gross profit @ Period(2027-03-01, 2027-05-15):      141.97

Quarterly statement
Start                       2026-01-01  2026-04-01  2026-07-01  2026-10-01
End             2026-01-01  2026-04-01  2026-07-01  2026-10-01  2027-01-01
    Revenue                     303.01      312.19      321.65      331.40
    COGS                       -151.50     -156.10     -160.83     -165.70
--------------------------------------------------------------------------
  Gross Profit                  151.50      156.10      160.83      165.70
  R&D                           -30.00      -30.00      -30.00      -30.00
  SGA                           -30.00      -30.00      -30.00      -30.00
--------------------------------------------------------------------------
Income                           91.50       96.10      100.83      105.70
```

## Layout

| File | Role |
| --- | --- |
| [`main.py`](main.py) | Defines monthly line items, composes them with arithmetic combinators, and prints quarterly results. |
