# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""TSA checkpoint volumes as a lazily fetched daily orcaset series."""

from datetime import date, timedelta
from operator import itemgetter

import requests
from bs4 import BeautifulSoup

from orcaset import Cell, Cons, Effect, Period, Series, accrue, get, unfold_cells

TSA_URL = "https://www.tsa.gov/travel/passenger-volumes"
_HEADERS = {
    "User-Agent": "orcaset-web-scraping-example/0.1 (+https://github.com/orcaset/orcaset-py)",
    "Accept": "text/html,application/xhtml+xml",
}
_BY_DAYS = accrue(lambda start, end: float((end - start).days))


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=_HEADERS, timeout=30.0)
    response.raise_for_status()
    return response.text


def parse_checkpoint_rows(html: str, url: str) -> list[tuple[date, float]]:
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
    # TSA publishes newest-first; unfold_cells requires strictly ascending keys.
    parsed.sort(key=itemgetter(0))
    return parsed


@Cell.define("Fetch and parse TSA checkpoints")
def checkpoint_step() -> Effect[Cons[Period, float] | None]:
    """Fetch the current-year page only when the series' first node is demanded."""
    html = fetch_html(TSA_URL)
    rows = parse_checkpoint_rows(html, TSA_URL)

    def step(index: int) -> tuple[Period, float, int] | None:
        if index == len(rows):
            return None
        travel_date, count = rows[index]
        period = Period(travel_date - timedelta(days=1), travel_date)
        return period, count, index + 1

    daily = unfold_cells("TSA checkpoint daily rows", seed=0, step=step)
    return (yield from get(daily))


tsa_passengers = Series("TSA checkpoint passengers", checkpoint_step, _BY_DAYS)


@Cell.define("TSA checkpoint last date")
def tsa_last_date() -> Effect[date]:
    node = yield from get(tsa_passengers.cells)
    if node is None:
        raise RuntimeError("TSA checkpoint series is empty")
    while True:
        next_node = yield from get(node.tail)
        if next_node is None:
            return node.key.end
        node = next_node
