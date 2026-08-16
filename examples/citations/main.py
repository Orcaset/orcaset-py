# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Cite a SpaceX 10-Q revenue fact, then annualize it with ``.map``."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Self
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from orcaset import Context, Period, PeriodSeries, exact, isna, map_some

CONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/"
    "CIK0001181412/us-gaap/RevenueFromContractWithCustomerExcludingAssessedTax.json"
)
FRAME = "CY2026Q2"
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
    """A float that carries EDGAR provenance. Arithmetic returns a plain float."""

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


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} is not a JSON object")
    return {str(key): item for key, item in value.items()}


def _as_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{label} is not a JSON array")
    return list(value)


def load_frame(url: str, frame: str) -> tuple[date, date, float, str]:
    """Return ``(start, end, value, accn)`` for the companyconcept row with ``frame``."""
    request = Request(url, headers=_HEADERS)
    try:
        with urlopen(request, timeout=30.0) as response:
            payload: object = json.loads(response.read().decode())
    except HTTPError as error:
        raise RuntimeError(
            f"SEC request failed ({error.code}). The companyconcept API requires an "
            "identifying User-Agent that includes a contact email."
        ) from error

    units = _as_mapping(_as_mapping(payload, "companyconcept").get("units"), "units")
    for raw in _as_list(units.get("USD"), "units.USD"):
        fact = _as_mapping(raw, "USD fact")
        if fact.get("frame") != frame:
            continue
        start, end, val, accn = (
            fact.get("start"),
            fact.get("end"),
            fact.get("val"),
            fact.get("accn"),
        )
        if not isinstance(start, str) or not isinstance(end, str) or not isinstance(accn, str):
            raise TypeError(f"{frame} is missing start, end, or accn")
        if not isinstance(val, int | float) or isinstance(val, bool):
            raise TypeError(f"{frame} value is not a number")
        return date.fromisoformat(start), date.fromisoformat(end), float(val), accn
    raise RuntimeError(f"no USD fact with frame {frame!r} at {url}")


@PeriodSeries.define("SpaceX revenue", exact)
def revenue() -> Iterator[tuple[Period, Cited]]:
    start, end, val, accn = load_frame(CONCEPT_URL, FRAME)
    yield (
        Period(start - timedelta(days=1), end),
        Cited(val, EdgarCitation(accn=accn, frame=FRAME, url=CONCEPT_URL)),
    )


annualized = revenue.map("Annualized revenue", map_some(lambda reported: reported * 4))


def main() -> None:
    ctx = Context()
    keys = list(ctx.get(revenue.keys()))
    if len(keys) != 1:
        raise RuntimeError(f"expected one SpaceX revenue period, got {len(keys)}")
    q2 = keys[0]

    reported = ctx.get_at(revenue, q2)
    run_rate = ctx.get_at(annualized, q2)
    if isna(reported) or isna(run_rate):
        raise RuntimeError("missing SpaceX revenue")

    print(f"Reported {FRAME} revenue: {reported}")
    print(f"  type: {type(reported).__name__}")
    print(f"Annualized (× 4):         {run_rate:,.0f}")
    print(f"  type: {type(run_rate).__name__}")
    print()
    print("Dependency tree for annualized revenue:")
    print(ctx.dependencies(annualized, q2))


if __name__ == "__main__":
    main()
