# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Cite a SpaceX 10-Q revenue fact, then grow it at 10% per quarter."""

import json
from dataclasses import dataclass
from datetime import date
from typing import Self, assert_type
from urllib.request import Request, urlopen

from dateutil.relativedelta import relativedelta

from orcaset import YF, Context, Maybe, Period, Series, Step, Thunk, accrual, get_at, isna

CONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/"
    "CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json"
)
FRAME = "CY2026Q2"
Q2_2026 = Period(date(2026, 3, 31), date(2026, 6, 30))
QUARTER = relativedelta(months=3, day=31)
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


class CitedFloat(float):
    """A float carrying EDGAR provenance; arithmetic returns a plain float."""

    citation: EdgarCitation
    __slots__ = ("citation",)

    def __new__(cls, value: float, citation: EdgarCitation) -> Self:
        obj = super().__new__(cls, value)
        obj.citation = citation
        return obj

    def __str__(self) -> str:
        return f"{float(self)} {self.citation}"

    def __repr__(self) -> str:
        return f"CitedFloat({float(self)!r}, {self.citation!r})"

    def __format__(self, spec: str) -> str:
        return str(self) if spec == "" else format(float(self), spec)


def load_frame(url: str, frame: str) -> CitedFloat:
    with urlopen(Request(url, headers=_HEADERS), timeout=30.0) as response:
        payload: object = json.load(response)
    assert isinstance(payload, dict)
    fact = next(row for row in payload["units"]["USD"] if row.get("frame") == frame)
    return CitedFloat(float(fact["val"]), EdgarCitation(fact["accn"], frame, url))


def revenue_step(period: Period) -> tuple[Period, float | Thunk[float], Period]:
    if period == Q2_2026:
        value: float | Thunk[float] = Thunk(lambda: load_frame(CONCEPT_URL, FRAME))
    else:

        def grow() -> Step[float]:
            prior = yield from get_at(revenue, period.from_start(-QUARTER))
            if isna(prior):
                raise ValueError(f"missing prior revenue for {period}")
            return prior * 1.10

        value = Thunk(grow)
    return period, value, period.from_end(QUARTER)


revenue: Series[Period, float, Maybe[float]] = Series.unfold(
    "SpaceX revenue", accrual(YF.cmonthly), seed=Q2_2026, step=revenue_step
)
assert_type(revenue, Series[Period, float, Maybe[float]])

ctx = Context()
for period in Period.seq(Q2_2026.start, QUARTER, date(2026, 12, 31)):
    print(f"{period} revenue: {ctx.get_at(revenue, period):,.0f}")

q2_revenue = ctx.get_at(revenue, Q2_2026)
print(f"\ntype(q2_2026_revenue): {type(q2_revenue)}")
if isinstance(q2_revenue, CitedFloat):
    print(f"Q2 2026 revenue citation: {q2_revenue.citation}\n")

Q3_2026 = Period(date(2026, 6, 30), date(2026, 9, 30))
print(f"Q3 2026 value type: {type(ctx.get_at(revenue, Q3_2026))}")
print(ctx.dependencies(revenue, Q3_2026))
