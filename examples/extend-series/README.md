# Extend Series

This example shows how you can extend series horizontally by nesting each segment in an outer series. This lets you extend historical data with projections or join other disjoint sections.

The basic pattern is to define an outer parent series that holds each segment, then flatten the parent into a joined series. Flattening preserves missing values and does not fill gaps.

In the example, there are three discrete revenue segments: historical `actuals`, explicit `projections`, and an infinite terminal revenue series that grows revenue at a 2% annual rate.

## Joining actuals and explicit projections

The actuals and explicit projections are defined from lists of period-float pairs. Notice that the projections overlap with the historical data and include a missing `Na` value in November. Also note that each segment series has a different query function. The actuals do not permit interpolation, while the projections are interpolated on an even monthly basis.

```py
historical = [(Q3, 300.0)]
projected = [(Q3, 0.0), (OCT, 110.0), (NOV, Na), (DEC, 121.0)]

actuals = Series.of("Actuals", covered, historical)  # `covered` query function
projections = Series.of("Projections", accrue_monthly, projected)  # `accrue_monthly` query function
```

First, define an outer `components` series that holds each segment. The outer series uses integer indices as keys and segment series as values.

```python
components = Series.of("Revenue components", exact, [(0, actuals), (1, projections)])
base = Series.flatten(
    "Actuals and projections", components.cells, query=covered, split_keys=period_split
)
```

The nested series and flattening are visible by examining the type signatures for `components` and `base`.

* `Segment` is a type alias for each component series. It doesn't matter what the series' underlying `cells` value is, only that its `query` function returns a `Maybe[float]`.
* `components` holds `Segment` series keyed by an `int` index, and its query function returns a `Segment` or `Na`.
* `base` flattens the outer series into a series with `Period`-`Maybe[float]` pairs and returns a `Maybe[float]` from its query function.

```py
type Segment = Series[Period, Any, Maybe[float]]

components: Series[int, Segment, Maybe[Segment]]
base: Series[Period, Maybe[float], Maybe[float]]
```

The flattened `base` series lazily looks through to the underlying component series when queried. This preserves each component’s interpolation rules. Queries within one segment use its query function; queries crossing segment boundaries are split, and `query=covered` sums the segment answers. For example, interpolated Q3 actuals are undefined, so querying a partial period in Q3 should return `Na`. This holds whether the query is entirely inside Q3 or crosses the end of Q3.

```py
partial_actual = Period(date(2025, 8, 31), Q3.end)
bad_crossing = Period(date(2025, 8, 31), OCT.end)
print(f"\nPartial actual ({partial_actual}):", ctx.get_at(base, partial_actual))
print(f"Bad seam crossing ({bad_crossing}):", ctx.get_at(base, bad_crossing))
# Partial actual (Period(2025-08-31, 2025-09-30)): Na
# Bad seam crossing (Period(2025-08-31, 2025-10-31)): Na
```

Additionally, boundaries are defined by key domains with transitions clipped to avoid overlap. Recall that the explicit projections include a Q3 value that overlaps with the actuals. Querying `base`'s Q3 value shows that the `actuals` correctly take precedence.

```py
print(f"\nBase Q3 value ({Q3}):", ctx.get_at(base, Q3))
# Base Q3 value (Period(2025-06-30, 2025-09-30)): 300.0
```

## Terminal growth extension

`base` joins two independent series. However, the terminal growth segment should depend on the segment before it, starting when the prior segment ends. It needs to be lazily created only when the outer parent series demands it.

The `Series.cells` mechanism already supports these requirements. Each tail is a lazy, effectful rule that is inert until it's demanded. The segments in an outer components series can be generated on demand with information from the prior series passed through.

In the example, the terminal revenue segment depends on when the prior segment ended. The `continue_series` constructor builds a sequence of two components: `base` and a lazy continuation. The continuation function accepts the last node from `base` and returns a new `Series`. An infinite base would never construct its continuation. The sequence can then be flattened back out to create a joined revenue series.

```py
def terminal_revenue(
    last_node: Cons[Period, Maybe[float]] | None,
) -> Series[Period, Maybe[float], Maybe[float]]:
    """Grow revenue each month at a 2% annual rate after the prior series ends."""
    # If there is no prior node (e.g., the prior series is empty), return an empty series.
    if last_node is None:
        return Series.of("Terminal growth", accrue_monthly, [])

    # Otherwise, grow revenue each month at a 2% annual rate after the prior series ends.
    # Note that this series is lazily bound to `revenue`.
    @Series.define("Terminal growth", accrue_monthly, seed=last_node.key)
    def growth(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
        prior_month = yield from get_at(revenue, period)
        value = multiply_some((prior_month, (1 + 0.02 * YF.cmonthly(*period))))
        return period.from_end(MONTH), value, period.from_end(MONTH)

    return growth


revenue = Series.flatten(
    "Revenue",
    continue_series("Revenue components", base, terminal_revenue),
    query=covered,
    split_keys=period_split,
)
```

The self-reference to `revenue` works because evaluation is lazy: each new month reads the previous month, with dependencies tracing back to the explicit projections.

The combined `revenue` series can be queried over any date range, looking through to the underlying segment series for values and interpolation rules.

```py
half_forecast = Period(DEC.start, date(2026, 1, 15))
print(f"\nCross projection-forecast seam ({half_forecast}):", ctx.get_at(revenue, half_forecast))
# Cross projection-forecast seam (Period(2025-11-30, 2026-01-15)): 179.6459677419355
```

## Run

```sh
uv run python examples/extend-series/main.py
```

Output:

```txt
Start                2025-06-30  2025-09-30  2025-10-31  2025-11-30  2025-12-31
End      2025-06-30  2025-09-30  2025-10-31  2025-11-30  2025-12-31  2026-01-31
Revenue                  300.00      110.00                  121.00      121.20

Partial actual (Period(2025-08-31, 2025-09-30)): Na
Bad seam crossing (Period(2025-08-31, 2025-11-30)): Na

Base Q3 value (Period(2025-06-30, 2025-09-30)): 300.0

Cross projection-forecast seam (Period(2025-11-30, 2026-01-15)): 179.6459677419355

Dependencies for Period(2025-12-31, 2026-01-31) revenue:
Revenue@Period(2025-12-31, 2026-01-31) = 121.20166666666667
  Revenue@Period(2025-11-30, 2025-12-31) = 121.0
    Actuals and projections@Period(2025-11-30, 2025-12-31) = 121.0
      Projections@Period(2025-11-30, 2025-12-31) = 121.0
  Terminal growth@Period(2025-12-31, 2026-01-31) = 121.20166666666667
    Revenue@Period(2025-11-30, 2025-12-31) = 121.0
      Actuals and projections@Period(2025-11-30, 2025-12-31) = 121.0
        Projections@Period(2025-11-30, 2025-12-31) = 121.0
```
