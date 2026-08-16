# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Cite a SpaceX 10-Q revenue fact, then grow it at 10% per quarter."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Self
from urllib.request import Request, urlopen

from dateutil.relativedelta import relativedelta

from orcaset import (
    CellFactory,
    Context,
    Period,
    PeriodSeries,
    Step,
    exact,
    get_at,
    isna,
)

CONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/"
    "CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json"
)
FRAME = "CY2026Q2"
QUARTER = relativedelta(months=3, day=31)
GROWTH = 0.10
FORECAST_END = date(2027, 6, 30)
_HEADERS = {
    "User-Agent": "Orcaset Citations Example contact@orcaset.com",
    "Accept": "application/json",
}


@dataclass(frozen=True, slots=True)
class EdgarCitation:
    accn: str
    frame: str
    url: str

    def __str__(self) -> str:
        return str({"accn": self.accn, "frame": self.frame, "url": self.url})


class Cited(float):
    """A floating point number that carries EDGAR provenance. Arithmetic returns a plain float."""

    citation: EdgarCitation
    __slots__ = ("citation",)

    def __new__(cls, value: float, citation: EdgarCitation) -> Self:
        obj = super().__new__(cls, value)
        obj.citation = citation
        return obj

    def __str__(self) -> str:
        return f"{float(self)} {self.citation}"

    def __repr__(self) -> str:
        return f"Cited({float(self)!r}, {self.citation!r})"

    def __format__(self, spec: str) -> str:
        if spec == "":
            return str(self)
        return format(float(self), spec)


def load_frame(url: str, frame: str) -> tuple[date, date, float, str]:
    """Return ``(start, end, value, accn)`` for the companyconcept row with ``frame``."""
    with urlopen(Request(url, headers=_HEADERS), timeout=30.0) as response:
        payload: object = json.load(response)
    assert isinstance(payload, dict)
    fact = next(row for row in payload["units"]["USD"] if row.get("frame") == frame)
    return (
        date.fromisoformat(fact["start"]),
        date.fromisoformat(fact["end"]),
        float(fact["val"]),
        fact["accn"],
    )


@PeriodSeries.define("SpaceX revenue", exact)
def revenue() -> Iterator[tuple[Period, float | CellFactory[float]]]:
    start, end, val, accn = load_frame(CONCEPT_URL, FRAME)
    seed = Period(start - timedelta(days=1), end)
    yield seed, Cited(val, EdgarCitation(accn=accn, frame=FRAME, url=CONCEPT_URL))

    for k in Period.seq(seed.end, QUARTER, FORECAST_END):

        def factory(p: Period = k) -> Step[float]:
            prior = yield from get_at(revenue, p.shift(-QUARTER))
            if isna(prior):
                raise ValueError(f"missing prior revenue for {p}")
            return prior * (1 + GROWTH)

        yield k, factory


def main() -> None:
    ctx = Context()
    periods = list(ctx.get(revenue.keys()))
    seed, *forecast = periods
    reported = ctx.get_at(revenue, seed)
    if isna(reported):
        raise RuntimeError("missing SpaceX revenue")

    print(f"Reported {FRAME} revenue: {reported}")
    print(f"  type: {type(reported).__name__}")
    print()
    print("Revenue by quarter-end (10% growth after the cited seed)")
    for period in periods:
        value = ctx.get_at(revenue, period)
        if isna(value):
            raise RuntimeError(f"missing SpaceX revenue for {period}")
        print(f"  {period.end:%Y-%m-%d}  {float(value):,.0f}  {type(value).__name__}")
    print()
    print("Dependency tree for the first forecast quarter:")
    print(ctx.dependencies(revenue, forecast[0]))


if __name__ == "__main__":
    main()
