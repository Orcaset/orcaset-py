# Web Fetch Example

*Run from the repo root: `uv run python examples/web-fetch/main.py`. Code: [main.py](./main.py).*

It is easy to pull data from third-party sources into Orcaset models. The Python ecosystem has great libraries for data retrieval and manipulation over a wide range of data formats.

This example highlights data retrieval over the web by fetching historical revenue data for Alphabet from the SEC. The SEC API is used in this example because it is free and unauthenticated, so it is easy to reproduce.

## Statement structure

```text
Revenue: Historical 2024 and 2025. Grows annually by the historical 2024 to 2025 growth rate thereafter.
YoY Growth Rate: Year-over-year growth rate.
```

## Assumptions

| Input | Value |
| --- | --- |
| **Company** | Alphabet Inc. (CIK 0001652044) |
| **Historical years** | FY2024 and FY2025, from SEC `us-gaap/Revenues` |
| **Growth** | FY2024 to FY2025 revenue growth, annually from FY2026 onward |
| **Forecast horizon** | FY2026 through FY2028 |

## Fetching data

This example uses the built-in `urllib.request` HTTP client so that it doesn't depend on any third-party libraries.

First, define a function `fetch_sec_data` that gets and parses data for a given company ID, financial concept, and year-end date.

```py
ALPHABET_CIK = "0001652044"  # SEC company ID
REVENUE_CONCEPT = "Revenues"  # Line item to get, using XBRL taxonomy

# See https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
SEC_USER_AGENT = "orcaset-py web-fetch example"


def fetch_sec_data(cik: str, concept: str, fiscal_year_end: date) -> float:
    """Load annual data for a fiscal year from SEC XBRL company-concept API."""
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"
    request = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    end = fiscal_year_end.isoformat()
    for fact in payload["units"]["USD"]:
        if fact.get("fp") != "FY":
            continue
        if fact.get("end") != end:
            continue
        if fact.get("form") not in ("10-K", "10-K/A"):
            continue
        return float(fact["val"])

    raise RuntimeError(f"No annual {concept} fact found for CIK {cik} with fiscal year end {end}")
```

The API returns a JSON payload with a timeseries of the concept for every report filed by the company. This function parses the JSON object, finds the 10-K filing for the requested fiscal year, and extracts the value.

You can run this model for different companies or line items by passing different `cik` or `concept` parameters. All changes will flow through correctly. Note that the concept taxonomy may differ across companies.

Use this function to create a list of historical revenue.

```py
historical_revenue_values = [
    (period, fetch_sec_data(ALPHABET_CIK, REVENUE_CONCEPT, period.end))
    for period in Period.seq(date(2023, 12, 31), relativedelta(years=1), date(2025, 12, 31))
]
```

## Revenue model

The revenue model is simple.

Calculate the growth rate assumption from the last two years of historicals.

```py
revenue_growth_rate = (historical_revenue_values[1][1] / historical_revenue_values[0][1]) - 1
```

Create a series from the list of historical revenue values.

```py
HistoricalRevenue = span.from_list(historical_revenue_values, agg=sum_spans(0.0))
```

Extend the revenue series by growing at a constant annual rate.

```py
@span.extend(HistoricalRevenue)
def Revenue(self: SpanSeries, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, relativedelta(years=1)):
        lookback_period = period.from_start(relativedelta(years=-1))
        prior_value = self.ctx.get(Revenue).value(lookback_period)
        yield Span(period, prior_value * (1 + revenue_growth_rate), split_daily)
```

Create a new point series to confirm the YoY growth rate.

```py
class RevenueGrowth(PointSeries):
    label = "YoY Growth Rate"

    def point(self, dt: date) -> Formula[float | None]:
        current = self.ctx.get(Revenue).value(Period(dt - relativedelta(years=1), dt))
        prior = self.ctx.get(Revenue).value(
            Period(dt - relativedelta(years=2), dt - relativedelta(years=1))
        )
        return current.map2(
            prior,
            lambda c, p: None if c is None or p in (None, 0) else (c / p) - 1,
        )
```

## Printing outputs

Put both the revenue and revenue growth series in a statement.

```py
stmt = Stmt(Revenue, RevenueGrowth)
```

To make numbers easier to read, we'll define a number formatter that prints small numbers as percentages.

```py
def format_value(value: float | None) -> str:
    if value is None:
        return ""
    if abs(value) < 10:
        return f"{value:.1%}"
    return f"{value / 1e6:,.0f}"
```

Printing the historicals and three years of projections returns the table below:

```py
ctx = Context()
periods = Period.list(date(2023, 12, 31), relativedelta(years=1), date(2028, 12, 31))
results = stmt.values(ctx, periods)
print(
    fixed_width_table(
        results,
        date_formatter=lambda dt: f"{dt:%Y-%m-%d}",
        value_formatter=format_value,
    )
)

# Start                        2023-12-31  2024-12-31  2025-12-31  2026-12-31  2027-12-31
# End              2023-12-31  2024-12-31  2025-12-31  2026-12-31  2027-12-31  2028-12-31
# Revenue                         350,018     402,836     463,624     533,586     614,104
# YoY Growth Rate                               15.1%       15.1%       15.1%       15.1%
```

## Additional considerations

This model is purposely very simple, but the core concepts apply to larger models. 

### Authentication

Use best security practices. Keep API keys secure, for example as in a `.env` file for local development, not as hardcoded values in models.

### Batch requests

Batch network requests. For example, this example fetches all historical data up front (and could be improved by pulling all historicals from the same response) rather than on-demand when cells are materialized. In addition to faster execution time, batching requests reduces the likelihood of failures from API rate limits.

