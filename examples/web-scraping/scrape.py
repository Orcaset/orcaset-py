# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""TSA checkpoint volumes as a daily orcaset series.

Fetching runs when the series cells are first demanded in a ``Context``, so
the revenue model can ``get_at`` passenger counts like any other line item.
"""

import re
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
_ARCHIVE_YEAR = re.compile(r"/travel/passenger-volumes/(\d{4})")
_BY_DAYS = accrual(lambda start, end: float((end - start).days))
_FIRST_REPORTING_YEAR = 2025


def _get(url: str) -> str:
    response = httpx.get(url, headers=_HEADERS, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _parse_rows(html: str, url: str) -> list[tuple[date, float]]:
    soup = BeautifulSoup(html, "html.parser")
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
    return parsed


def checkpoint_volumes(url: str = TSA_URL) -> list[tuple[date, float]]:
    """Download current and archived TSA tables as ``(travel date, passengers)``."""
    html = _get(url)
    by_date = dict(_parse_rows(html, url))
    for year_text in sorted(set(_ARCHIVE_YEAR.findall(html))):
        if int(year_text) < _FIRST_REPORTING_YEAR:
            continue
        archive_url = f"{url.rstrip('/')}/{year_text}"
        by_date.update(_parse_rows(_get(archive_url), archive_url))
    if not by_date:
        raise RuntimeError(f"no checkpoint rows parsed from {url}")
    return sorted(by_date.items())


@PeriodSeries.define("TSA checkpoint passengers", _BY_DAYS)
def tsa_passengers() -> Iterator[tuple[Period, float]]:
    for travel_date, count in checkpoint_volumes():
        yield Period(travel_date - timedelta(days=1), travel_date), count
