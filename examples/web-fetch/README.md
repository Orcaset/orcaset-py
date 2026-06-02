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
def revenue(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, relativedelta(years=1)):
        lookback_period = period.from_start(relativedelta(years=-1))
        prior_value = revenue.value(ctx, lookback_period)
        yield Span(period, prior_value * (1 + revenue_growth_rate), split_daily)
```

Point series use `@point.define` and return a value formula for the query date:

```py
@point.define(label="YoY Growth Rate")
def revenue_growth(ctx: Context, dt: date) -> Formula[float | None]:
    current = revenue.value(ctx, Period(dt - relativedelta(years=1), dt))
    prior = revenue.value(ctx, Period(dt - relativedelta(years=2), dt - relativedelta(years=1)))
    return current.map2(prior, lambda c, p: None if c is None or p in (None, 0) else (c / p) - 1)
```

Run the example:

```sh
uv run python examples/web-fetch/main.py
```
