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
    Chain,
    Cons,
    Effect,
    Fn,
    Period,
    Series,
    Thunk,
    get,
    get_at,
    ops,
    period_union,
    query,
    stmt,
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
@Fn.define(name="TSA nowcast windows")
def nowcast_windows() -> Effect[tuple[Period, Period]]:
    last_observation = yield from get(tsa_last_date)
    current = NOWCAST_QUARTER
    if last_observation <= current.start:
        raise ValueError(f"last TSA date {last_observation.isoformat()} is before {current}")
    # Once TSA data runs past the nowcast quarter, compare the full quarters.
    qtd_end = min(last_observation, current.end)
    prior = current.shift(-QUARTER)
    return Period(current.start, qtd_end), Period(prior.start, prior.start + (qtd_end - current.start))


passenger_history = Series.of(
    ACCRUE,
    [(period, values["passenger_revenue"]) for period, values in HISTORY],
    name="Passenger history",
)
freight_history = Series.of(
    ACCRUE, [(period, values["freight"]) for period, values in HISTORY], name="Freight history"
)
other_history = Series.of(
    ACCRUE, [(period, values["other"]) for period, values in HISTORY], name="Other history"
)


@Series.define(ACCRUE, seed=NOWCAST_QUARTER, name="Passenger forecast")
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
    ACCRUE, base=passenger_history.cells, cont=lambda _: passenger_forecast.cells, name="Passenger"
)


def constant_forecast(last: Cons[Period, float] | None) -> Chain[Period, float]:
    if last is None:
        raise ValueError("missing revenue history")
    return unfold_cells(
        seed=last.key.from_end(QUARTER),
        step=lambda period: (period, Thunk(lambda: get(last.value)), period.from_end(QUARTER)),
        name="Held forecast",
    )


freight = Series.extend(ACCRUE, base=freight_history.cells, cont=constant_forecast, name="Freight")
other = Series.extend(ACCRUE, base=other_history.cells, cont=constant_forecast, name="Other")
total_operating_revenue = ops.add(
    passenger,
    freight,
    other,
    merge_keys=period_union,
    name="Total operating revenue",
)

# ---- Statement definition ----
operating_revenue_stmt = stmt.Stmt(
    tsa_passengers,
    stmt.Total(total_operating_revenue, [passenger, freight, other]),
)
