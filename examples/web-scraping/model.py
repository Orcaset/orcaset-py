# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Southwest operating-revenue series from reported history and TSA checkpoint volumes.

Passenger revenue for the first unreported quarter is prior-quarter passenger
revenue times current QTD TSA volume over the same elapsed window of the prior
quarter, then held constant. Freight and other stay at their last reported
values.
"""

from collections.abc import Iterator
from csv import DictReader
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta
from scrape import tsa_passengers

from orcaset import (
    YF,
    CellStream,
    Period,
    PeriodSeries,
    Step,
    Stmt,
    Total,
    accrual,
    get,
    get_at,
    isna,
)

QUARTER = relativedelta(months=3, day=31)
ACCRUE = accrual(YF.cmonthly)
CSV_PATH = Path(__file__).resolve().parent / "data" / "luv_operating_revenue.csv"
COLUMNS = ("passenger_revenue", "freight", "other")


def parse_quarter_label(label: str) -> Period:
    tag, year_text = label.split()
    end = date(int(year_text), int(tag[1:]) * 3, 1) + relativedelta(day=31)
    return Period(end - QUARTER, end)


def load_history(path: Path = CSV_PATH) -> list[tuple[Period, dict[str, float]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            (
                parse_quarter_label(row["quarter"]),
                {column: float(row[column]) for column in COLUMNS},
            )
            for row in DictReader(handle)
        ]
    if not rows:
        raise RuntimeError(f"no revenue rows in {path}")
    return rows


HISTORY = load_history()
NOWCAST_QUARTER = HISTORY[-1][0].from_end(QUARTER)


def qtd_windows(current: Period, last_observation: date) -> tuple[Period, Period]:
    """Current-quarter QTD and the same elapsed window of the prior quarter."""
    if last_observation <= current.start or last_observation > current.end:
        raise ValueError(f"last TSA date {last_observation.isoformat()} is not inside {current}")
    prior = current.shift(-QUARTER)
    return Period(current.start, last_observation), Period(
        prior.start, prior.start + (last_observation - current.start)
    )


@PeriodSeries.define("Passenger", ACCRUE)
def passenger() -> CellStream[Period, float]:
    keys = yield from get(tsa_passengers.keys())
    days = list(keys)
    if not days:
        raise RuntimeError("TSA checkpoint series is empty")
    qtd, prior_qtd = qtd_windows(NOWCAST_QUARTER, days[-1].end)

    # Historical values
    for period, values in HISTORY:
        yield period, values["passenger_revenue"]

    # Current quarter estimated values using TSA volume
    def estimate(
        period: Period = NOWCAST_QUARTER,
        qtd_period: Period = qtd,
        prior_qtd_period: Period = prior_qtd,
    ) -> Step[float]:
        prior = yield from get_at(passenger, period.shift(-QUARTER))
        current_tsa = yield from get_at(tsa_passengers, qtd_period)
        prior_tsa = yield from get_at(tsa_passengers, prior_qtd_period)
        if isna(prior) or isna(current_tsa) or isna(prior_tsa):
            raise ValueError(f"missing TSA QTD inputs for passenger revenue at {period}")
        if prior_tsa == 0.0:
            raise ValueError("prior-quarter TSA QTD is zero")
        return prior * (current_tsa / prior_tsa)

    yield NOWCAST_QUARTER, estimate

    # Future values after the current quarter, held constant
    def hold() -> Step[float]:
        value = yield from get_at(passenger, NOWCAST_QUARTER)
        if isna(value):
            raise ValueError("missing current-quarter passenger revenue")
        return value

    for key in Period.seq(NOWCAST_QUARTER.end, QUARTER):
        yield key, hold


@PeriodSeries.define("Freight", ACCRUE)
def freight() -> Iterator[tuple[Period, float]]:
    """Historical values, then held constant."""
    for period, values in HISTORY:
        yield period, values["freight"]
    last_period, last_values = HISTORY[-1]
    for key in Period.seq(last_period.end, QUARTER):
        yield key, last_values["freight"]


@PeriodSeries.define("Other", ACCRUE)
def other() -> Iterator[tuple[Period, float]]:
    """Historical values, then held constant."""
    for period, values in HISTORY:
        yield period, values["other"]
    last_period, last_values = HISTORY[-1]
    for key in Period.seq(last_period.end, QUARTER):
        yield key, last_values["other"]

total_operating_revenue = (passenger + freight + other).named(
    "Total operating revenue"
)

operating_revenue_stmt = Stmt(
    tsa_passengers,
    Total(total_operating_revenue, [passenger, freight, other]),
)
