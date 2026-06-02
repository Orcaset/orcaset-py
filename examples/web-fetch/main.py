from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Period,
    Span,
    Stmt,
    fixed_width_table,
    point,
    split_daily,
    sum_spans,
    span,
)

# --------------- SEC DATA ---------------
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


historical_revenue_values = [
    (period, fetch_sec_data(ALPHABET_CIK, REVENUE_CONCEPT, period.end))
    for period in Period.seq(date(2023, 12, 31), relativedelta(years=1), date(2025, 12, 31))
]

# --------------- MODEL ---------------
revenue_growth_rate = (historical_revenue_values[1][1] / historical_revenue_values[0][1]) - 1

historical_revenue = span.from_list(historical_revenue_values, agg=sum_spans(0.0), label="Revenue")


@span.extend(historical_revenue)
def revenue(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, relativedelta(years=1)):
        lookback_period = period.from_start(relativedelta(years=-1))
        prior_value = revenue.value(ctx, lookback_period)
        yield Span(period, prior_value * (1 + revenue_growth_rate), split_daily)


@point.define(label="YoY Growth Rate")
def revenue_growth(ctx: Context, dt: date) -> Formula[float | None]:
    current = revenue.value(ctx, Period(dt - relativedelta(years=1), dt))
    prior = revenue.value(ctx, Period(dt - relativedelta(years=2), dt - relativedelta(years=1)))
    return current.map2(
        prior,
        lambda c, p: None if c is None or p in (None, 0) else (c / p) - 1,
    )


# --------------- OUTPUT ---------------
stmt = Stmt(revenue, revenue_growth)


def format_value(value: float | None) -> str:
    if value is None:
        return ""
    if abs(value) < 10:
        return f"{value:.1%}"
    return f"{value / 1e6:,.0f}"


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
