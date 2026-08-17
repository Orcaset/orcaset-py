# Series Composition

This example uses a simple income model to demonstrate concise series transformations using regular built-in arithmetic operators (e.g. `+`, `-`, `*`, etc).

## How It Works

Orcaset includes pre-built classes for working with data index by periods (`PeriodSeriesBase`) and dates (`DateSeriesBase`). These classes implement dunder methods for common arithmetic operations when series values are floats. This makes it easy to compose line items into complex models. For example, defining income as the sum of gross profit and operating expenses can be done with the `+` operator.

```py
income = (gross_profit + rd + sga).named("income")
```

This line adds the three component series together and assigns a human-readable name to the result.

Under the hood, series are combined using the `Map2` combinator which aligns input series based on keys (i.e. periods or dates) and sums values, interpolating partial periods if necessary.

## Run

From the repository root:

```sh
uv run python examples/series-composition/main.py
```

Running the script prints the outputs below.

```txt
  Revenue @ Period(2027-03-01, 2027-05-15):         283.94
  COGS @ Period(2027-03-01, 2027-05-15):           -141.97
----------------------------------------------------------
Gross profit @ Period(2027-03-01, 2027-05-15):      141.97

Quarterly statement
Start                       2026-01-01  2026-04-01  2026-07-01  2026-10-01
End             2026-01-01  2026-04-01  2026-07-01  2026-10-01  2027-01-01
    revenue                     303.01      312.19      321.65      331.40
    cogs                       -151.50     -156.10     -160.83     -165.70
--------------------------------------------------------------------------
  gross_profit                  151.50      156.10      160.83      165.70
  r&d                           -30.00      -30.00      -30.00      -30.00
  sga                           -30.00      -30.00      -30.00      -30.00
--------------------------------------------------------------------------
income                           91.50       96.10      100.83      105.70
```

## Layout

| File | Role |
| --- | --- |
| [`main.py`](main.py) | Defines the monthly line items, composes them with arithmetic operators, and prints quarterly results. |
