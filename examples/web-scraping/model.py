# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Southwest operating-revenue history and TSA-based nowcast."""

from csv import DictReader
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta
from scrape import tsa_last_date, tsa_passengers

from orcaset import (
    YF,
    Effect,
    Maybe,
    Period,
    Series,
    Stmt,
    Thunk,
    Total,
    accrue,
    get,
    get_at,
    isna,
    ops,
    period_union,
)

QUARTER = relativedelta(months=3, day=31)
ACCRUE = accrue(YF.cmonthly)
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
    if last_observation <= current.start or last_observation > current.end:
        raise ValueError(f"last TSA date {last_observation.isoformat()} is not inside {current}")
    prior = current.shift(-QUARTER)
    return Period(current.start, last_observation), Period(
        prior.start, prior.start + (last_observation - current.start)
    )


type ForecastState = int | Period


def passenger_step(
    state: ForecastState,
) -> Effect[tuple[Period, float | Thunk[float], ForecastState]]:
    if isinstance(state, int) and state < len(HISTORY):
        period, values = HISTORY[state]
        return period, values["passenger_revenue"], state + 1

    if isinstance(state, int):
        qtd, prior_qtd = qtd_windows(NOWCAST_QUARTER, (yield from get(tsa_last_date)))

        def estimate() -> Effect[float]:
            prior = yield from get_at(passenger, NOWCAST_QUARTER.shift(-QUARTER))
            current_tsa = yield from get_at(tsa_passengers, qtd)
            prior_tsa = yield from get_at(tsa_passengers, prior_qtd)
            if isna(prior) or isna(current_tsa) or isna(prior_tsa):
                raise ValueError("missing TSA QTD inputs for passenger revenue")
            if prior_tsa == 0.0:
                raise ValueError("prior-quarter TSA QTD is zero")
            return prior * (current_tsa / prior_tsa)

        return NOWCAST_QUARTER, Thunk(estimate), NOWCAST_QUARTER.from_end(QUARTER)

    period = state

    def hold() -> Effect[float]:
        value = yield from get_at(passenger, NOWCAST_QUARTER)
        if isna(value):
            raise ValueError("missing current-quarter passenger revenue")
        return value

    return period, Thunk(hold), period.from_end(QUARTER)


passenger: Series[Period, float, Maybe[float]] = Series.unfold(
    "Passenger", ACCRUE, seed=0, step=passenger_step
)


def held_series(name: str, column: str) -> Series[Period, float, Maybe[float]]:
    def step(state: ForecastState) -> tuple[Period, float, ForecastState]:
        if isinstance(state, int) and state < len(HISTORY):
            period, values = HISTORY[state]
            return period, values[column], state + 1
        period = HISTORY[-1][0].from_end(QUARTER) if isinstance(state, int) else state
        return period, HISTORY[-1][1][column], period.from_end(QUARTER)

    return Series.unfold(name, ACCRUE, seed=0, step=step)


freight = held_series("Freight", "freight")
other = held_series("Other", "other")
total_operating_revenue = ops.add(
    "Total operating revenue",
    passenger,
    freight,
    other,
    merge_keys=period_union,
)

operating_revenue_stmt = Stmt(
    tsa_passengers,
    Total(total_operating_revenue, [passenger, freight, other]),
)
