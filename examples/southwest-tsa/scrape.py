# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""TSA checkpoint volumes as a daily orcaset series.

Fetching and parsing run when the series cells are first demanded in a
``Context``, so the revenue model can ``get_at`` passenger counts the same way
it reads any other line item.
"""

from collections.abc import Iterator
from datetime import date, timedelta
from operator import itemgetter

import httpx
from bs4 import BeautifulSoup

from orcaset import Period, PeriodSeries, accrual

TSA_URL = "https://www.tsa.gov/travel/passenger-volumes"
_HEADERS = {
    "User-Agent": "orcaset-southwest-tsa-example/0.1 (+https://github.com/orcaset/orcaset-py)",
    "Accept": "text/html,application/xhtml+xml",
}
_BY_DAYS = accrual(lambda start, end: float((end - start).days))


def fetch_checkpoint_html(url: str = TSA_URL) -> str:
    """Download the TSA passenger-volumes page."""
    response = httpx.get(url, headers=_HEADERS, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.text


def parse_checkpoint_volumes(html: str) -> list[tuple[date, float]]:
    """Parse ``(travel date, checkpoint passengers)`` rows from the TSA table."""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table", limit=1)
    if not tables:
        raise RuntimeError(f"no checkpoint table found at {TSA_URL}")

    parsed: list[tuple[date, float]] = []
    seen: set[date] = set()
    for row in tables[0].select("tbody tr"):
        cells = [cell.get_text(strip=True) for cell in row.find_all("td")]
        if len(cells) < 2:
            continue
        month_text, day_text, year_text = cells[0].split("/")
        travel_date = date(int(year_text), int(month_text), int(day_text))
        if travel_date in seen:
            continue
        seen.add(travel_date)
        parsed.append((travel_date, float(cells[1].replace(",", ""))))

    parsed.sort(key=itemgetter(0))
    if not parsed:
        raise RuntimeError(f"no checkpoint rows parsed from {TSA_URL}")
    return parsed


def travel_day(travel_date: date) -> Period:
    """Map a TSA travel date onto an exclusive-start, inclusive-end day period."""
    return Period(travel_date - timedelta(days=1), travel_date)


@PeriodSeries.define("TSA checkpoint passengers", _BY_DAYS)
def tsa_passengers() -> Iterator[tuple[Period, float]]:
    for travel_date, count in parse_checkpoint_volumes(fetch_checkpoint_html()):
        yield travel_day(travel_date), count
