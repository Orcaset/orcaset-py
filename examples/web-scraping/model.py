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
    Cell,
    Cells,
    Cons,
    Effect,
    Period,
    Series,
    Stmt,
    Thunk,
    Total,
    get,
    get_at,
    ops,
    period_union,
    query,
    unfold_cells,
)
from orcaset.maybe import Maybe, isna, mul_some

# ---- Assumptions and history ----
QUARTER = relativedelta(months=3, day=31)
ACCRUE = query.accrue(YF.cmonthly)
CSV_PATH = Path(__file__).resolve().parent / "data" / "luv_operating_revenue.csv"
COLUMNS = ("passenger_revenue", "freight", "other")


HISTORY: list[tuple[Period, dict[str, float]]] = []
with CSV_PATH.open(newline="", encoding="utf-8") as handle:
    for row in DictReader(handle):
        tag, year_text = row["quarter"].split()
        end = date(int(year_text), int(tag[1:]) * 3, 1) + relativedelta(day=31)
        HISTORY.append(
            (Period(end - QUARTER, end), {column: float(row[column]) for column in COLUMNS})
        )
if not HISTORY:
    raise RuntimeError(f"no revenue rows in {CSV_PATH}")

NOWCAST_QUARTER = HISTORY[-1][0].from_end(QUARTER)


# ---- Model definitions ----
@Cell.define("TSA nowcast windows")
def nowcast_windows() -> Effect[tuple[Period, Period]]:
    last_observation = yield from get(tsa_last_date)
    current = NOWCAST_QUARTER
    if last_observation <= current.start or last_observation > current.end:
        raise ValueError(f"last TSA date {last_observation.isoformat()} is not inside {current}")
    prior = current.shift(-QUARTER)
    return Period(current.start, last_observation), Period(
        prior.start, prior.start + (last_observation - current.start)
    )


passenger_history = Series.of(
    "Passenger history",
    ACCRUE,
    [(period, values["passenger_revenue"]) for period, values in HISTORY],
)
freight_history = Series.of(
    "Freight history", ACCRUE, [(period, values["freight"]) for period, values in HISTORY]
)
other_history = Series.of(
    "Other history", ACCRUE, [(period, values["other"]) for period, values in HISTORY]
)


@Series.define("Passenger forecast", ACCRUE, seed=NOWCAST_QUARTER)
def passenger_forecast(period: Period) -> Effect[tuple[Period, Maybe[float], Period]]:
    if period == NOWCAST_QUARTER:
        prior_rev = yield from get_at(passenger_history, period.shift(-QUARTER))
        qtd, prior_qtd = yield from get(nowcast_windows)
        current_tsa = yield from get_at(tsa_passengers, qtd)
        prior_tsa = yield from get_at(tsa_passengers, prior_qtd)
        if prior_tsa == 0.0 or isna(prior_tsa):
            raise ValueError("prior-quarter TSA QTD is zero or missing")
        traffic_growth = mul_some(current_tsa, 1 / prior_tsa)
        value = mul_some(prior_rev, traffic_growth)
    else:
        value = yield from get_at(passenger_forecast, NOWCAST_QUARTER)

    return period, value, period.from_end(QUARTER)


passenger = Series.extend(
    "Passenger", ACCRUE, base=passenger_history.cells, cont=lambda _: passenger_forecast.cells
)


def constant_forecast(last: Cons[Period, float] | None) -> Cells[Period, float]:
    if last is None:
        raise ValueError("missing revenue history")
    return unfold_cells(
        "Held forecast",
        seed=last.key.from_end(QUARTER),
        step=lambda period: (period, Thunk(lambda: get(last.cell)), period.from_end(QUARTER)),
    )


freight = Series.extend("Freight", ACCRUE, base=freight_history.cells, cont=constant_forecast)
other = Series.extend("Other", ACCRUE, base=other_history.cells, cont=constant_forecast)
total_operating_revenue = ops.add(
    "Total operating revenue",
    passenger,
    freight,
    other,
    merge_keys=period_union,
)

# ---- Statement definition ----
operating_revenue_stmt = Stmt(
    tsa_passengers,
    Total(total_operating_revenue, [passenger, freight, other]),
)
