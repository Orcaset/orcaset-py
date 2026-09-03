# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""TSA checkpoint volumes as a lazily fetched daily orcaset series."""

import re
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from orcaset import Cell, Period, Series, Step, accrual, get

TSA_URL = "https://www.tsa.gov/travel/passenger-volumes"
_HEADERS = {
    "User-Agent": "orcaset-web-scraping-example/0.1 (+https://github.com/orcaset/orcaset-py)",
    "Accept": "text/html,application/xhtml+xml",
}
_ARCHIVE_YEAR = re.compile(r"/travel/passenger-volumes/(\d{4})")
_BY_DAYS = accrual(lambda start, end: float((end - start).days))
_FIRST_REPORTING_YEAR = 2026


def _get(url: str) -> str:
    response = requests.get(url, headers=_HEADERS, timeout=30.0)
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


def checkpoint_pairs() -> list[tuple[Period, float]]:
    return [
        (Period(travel_date - timedelta(days=1), travel_date), count)
        for travel_date, count in checkpoint_volumes()
    ]


type CheckpointState = None | tuple[list[tuple[Period, float]], int]


def checkpoint_step(
    state: CheckpointState,
) -> tuple[Period, float, CheckpointState] | None:
    pairs, index = (checkpoint_pairs(), 0) if state is None else state
    if index == len(pairs):
        return None
    period, count = pairs[index]
    return period, count, (pairs, index + 1)


tsa_passengers = Series.unfold(
    "TSA checkpoint passengers",
    _BY_DAYS,
    seed=None,
    step=checkpoint_step,
)


def find_last_date() -> Step[date]:
    node = yield from get(tsa_passengers.cells)
    if node is None:
        raise RuntimeError("TSA checkpoint series is empty")
    while True:
        next_node = yield from get(node.tail)
        if next_node is None:
            return node.key.end
        node = next_node


tsa_last_date = Cell("TSA checkpoint last date", find_last_date)
