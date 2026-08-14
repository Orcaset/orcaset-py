# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""TSA checkpoint volumes as a daily orcaset series.

Fetching runs when the series cells are first demanded in a ``Context``, so
the revenue model can ``get_at`` passenger counts like any other line item.
"""

from collections.abc import Iterator
from datetime import date, timedelta

import httpx
from bs4 import BeautifulSoup

from orcaset import Period, PeriodSeries, accrual

TSA_URL = "https://www.tsa.gov/travel/passenger-volumes"
_HEADERS = {
    "User-Agent": "orcaset-web-scraping-example/0.1 (+https://github.com/orcaset/orcaset-py)",
    "Accept": "text/html,application/xhtml+xml",
}
_BY_DAYS = accrual(lambda start, end: float((end - start).days))


def checkpoint_volumes(url: str = TSA_URL) -> list[tuple[date, float]]:
    """Download and parse ``(travel date, checkpoint passengers)`` rows."""
    response = httpx.get(url, headers=_HEADERS, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table", limit=1)
    if not tables:
        raise RuntimeError(f"no checkpoint table found at {url}")

    parsed: list[tuple[date, float]] = []
    for row in tables[0].select("tbody tr"):
        cells = [cell.get_text(strip=True) for cell in row.find_all("td")]
        if len(cells) < 2:
            continue
        month_text, day_text, year_text = cells[0].split("/")
        parsed.append(
            (
                date(int(year_text), int(month_text), int(day_text)),
                float(cells[1].replace(",", "")),
            )
        )
    parsed.sort()
    if not parsed:
        raise RuntimeError(f"no checkpoint rows parsed from {url}")
    return parsed


@PeriodSeries.define("TSA checkpoint passengers", _BY_DAYS)
def tsa_passengers() -> Iterator[tuple[Period, float]]:
    for travel_date, count in checkpoint_volumes():
        yield Period(travel_date - timedelta(days=1), travel_date), count
