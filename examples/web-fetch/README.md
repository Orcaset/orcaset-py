# Web Fetch

This example loads historical Alphabet revenue from the SEC company-concept API, extends it with a forecast, and calculates year-over-year growth.

The historical series is a helper-created def:

```py
historical_revenue = span.from_list(
    historical_revenue_values,
    agg=sum_spans(0.0),
    label="Revenue",
)
```

The forecast uses `span.extend(...)`, which appends generated spans after the historical data:

```py
@span.extend(historical_revenue)
def revenue(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, relativedelta(years=1)):
        lookback_period = period.from_start(relativedelta(years=-1))
        prior_value = revenue.value(ctx, lookback_period)
        yield Span(period, prior_value * (1 + revenue_growth_rate), split_daily)
```

Derived point series can compute every requested date through interpolation:

```py
@point.derived(label="YoY Growth Rate")
def revenue_growth(ctx: Context, dt: date) -> Formula[float | None]:
    current = revenue.value(ctx, Period(dt - relativedelta(years=1), dt))
    prior = revenue.value(ctx, Period(dt - relativedelta(years=2), dt - relativedelta(years=1)))
    return current.map2(prior, lambda c, p: None if c is None or p in (None, 0) else (c / p) - 1)
```

Run the example:

```sh
uv run python examples/web-fetch/main.py
```
