# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Southwest operating-revenue series: reported history, TSA nowcast, seasonal forecast.

Passenger lines for the first unreported quarter scale last quarter by the TSA
checkpoint QTD change versus the same elapsed window of the prior quarter.
Later quarters apply last year's corresponding QoQ seasonal ratio. Freight and
other hold the last reported value in the current quarter, then follow the
same seasonal path.
"""

from collections.abc import Iterator
from csv import DictReader
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta
from scrape import tsa_passengers

from orcaset import (
    YF,
    CellFactory,
    CellStream,
    Maybe,
    Period,
    PeriodSeries,
    PeriodSeriesBase,
    Step,
    Stmt,
    Total,
    accrual,
    exact,
    get,
    get_at,
    isna,
)

QUARTER = relativedelta(months=3, day=31)
YEAR = relativedelta(years=1)
ACCRUE = accrual(YF.cmonthly)
CSV_PATH = Path(__file__).resolve().parent / "data" / "luv_operating_revenue.csv"
COLUMNS = (
    "passenger_non_loyalty",
    "loyalty_air_transport",
    "ancillary",
    "freight",
    "other",
)


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


@PeriodSeries.define("TSA QTD factor", exact)
def tsa_qtd_factor() -> CellStream[Period, float]:
    keys = yield from get(tsa_passengers.keys())
    days = list(keys)
    if not days:
        raise RuntimeError("TSA checkpoint series is empty")
    qtd, prior_qtd = qtd_windows(NOWCAST_QUARTER, days[-1].end)

    def factory() -> Step[float]:
        current_tsa = yield from get_at(tsa_passengers, qtd)
        prior_tsa = yield from get_at(tsa_passengers, prior_qtd)
        if isna(current_tsa) or isna(prior_tsa):
            raise ValueError("missing TSA QTD volumes")
        if prior_tsa == 0.0:
            raise ValueError("prior-quarter TSA QTD is zero")
        return current_tsa / prior_tsa

    yield NOWCAST_QUARTER, factory


def _line_item(name: str, column: str, *, scale_with_tsa: bool) -> PeriodSeries[Maybe[float]]:
    @PeriodSeries.define(name, ACCRUE)
    def series() -> Iterator[tuple[Period, float | CellFactory[float]]]:
        for period, values in HISTORY:
            yield period, values[column]

        def nowcast(period: Period = NOWCAST_QUARTER) -> Step[float]:
            prior = yield from get_at(series, period.shift(-QUARTER))
            if isna(prior):
                raise ValueError(f"missing {name} for {period.shift(-QUARTER)}")
            if not scale_with_tsa:
                return prior
            factor = yield from get_at(tsa_qtd_factor, period)
            if isna(factor):
                raise ValueError(f"missing TSA QTD factor for {name} at {period}")
            return prior * factor

        yield NOWCAST_QUARTER, nowcast

        for key in Period.seq(NOWCAST_QUARTER.end, QUARTER):

            def factory(period: Period = key) -> Step[float]:
                prior = yield from get_at(series, period.shift(-QUARTER))
                seasonal_num = yield from get_at(series, period.shift(-YEAR))
                seasonal_den = yield from get_at(series, period.shift(-YEAR).shift(-QUARTER))
                if isna(prior) or isna(seasonal_num) or isna(seasonal_den):
                    raise ValueError(f"missing seasonal inputs for {name} at {period}")
                if seasonal_den == 0.0:
                    raise ValueError(f"zero seasonal denominator for {name} at {period}")
                return prior * (seasonal_num / seasonal_den)

            yield key, factory

    return series


passenger_non_loyalty = _line_item(
    "Passenger non-loyalty", "passenger_non_loyalty", scale_with_tsa=True
)
loyalty_air_transport = _line_item(
    "Loyalty – air transport", "loyalty_air_transport", scale_with_tsa=True
)
ancillary = _line_item("Ancillary", "ancillary", scale_with_tsa=True)
freight = _line_item("Freight", "freight", scale_with_tsa=False)
other = _line_item("Other", "other", scale_with_tsa=False)

passenger_revenue: PeriodSeriesBase[Maybe[float]] = (
    passenger_non_loyalty + loyalty_air_transport + ancillary
).named("Passenger revenue")
total_operating_revenue: PeriodSeriesBase[Maybe[float]] = (
    passenger_revenue + freight + other
).named("Total operating revenue")

operating_revenue_stmt = Stmt(
    Total(
        total_operating_revenue,
        [
            Total(
                passenger_revenue,
                [passenger_non_loyalty, loyalty_air_transport, ancillary],
            ),
            freight,
            other,
        ],
    )
)
