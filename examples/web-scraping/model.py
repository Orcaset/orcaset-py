# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Southwest operating-revenue series: reported history, TSA nowcast, seasonal forecast.

Passenger lines for the unreported current quarter scale last quarter by the
TSA checkpoint QTD change versus the same elapsed window of the prior quarter.
Later quarters apply last year's corresponding quarter-on-quarter seasonal
ratio to that nowcast. Freight and other hold the last reported value in the
current quarter, then follow the same seasonal path.
"""

from collections.abc import Callable, Iterable
from csv import DictReader
from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from scrape import tsa_passengers

from orcaset import (
    YF,
    CellStream,
    Context,
    Maybe,
    Period,
    PeriodSeries,
    PeriodSeriesBase,
    Step,
    Stmt,
    Total,
    accrual,
    get,
    get_at,
    isna,
)

QUARTER = relativedelta(months=3, day=31)
YEAR = relativedelta(years=1)
ACCRUE = accrual(YF.cmonthly)
CSV_PATH = Path(__file__).resolve().parent / "data" / "luv_operating_revenue.csv"
OUTPUT_START = date(2024, 12, 31)
EASTERN = ZoneInfo("America/New_York")

type LineGetter = Callable[[ReportedQuarter], float]


@dataclass(frozen=True, slots=True)
class ReportedQuarter:
    period: Period
    passenger_non_loyalty: float
    loyalty_air_transport: float
    ancillary: float
    freight: float
    other: float


@dataclass(frozen=True, slots=True)
class NowcastSpec:
    current_quarter: Period
    prior_quarter: Period
    qtd: Period
    prior_qtd: Period


def quarter_period(year: int, quarter: int) -> Period:
    if quarter not in {1, 2, 3, 4}:
        raise ValueError(f"invalid quarter {quarter}")
    end_month = quarter * 3
    end = date(year, end_month, 1) + relativedelta(day=31)
    return Period(end - QUARTER, end)


def parse_quarter_label(label: str) -> Period:
    tag, year_text = label.split()
    return quarter_period(int(year_text), int(tag[1:]))


def as_of_date() -> date:
    return datetime.now(EASTERN).date()


def quarter_containing(day: date) -> Period:
    return quarter_period(day.year, (day.month - 1) // 3 + 1)


def quarter_label(day: date) -> str:
    return f"Q{(day.month - 1) // 3 + 1} {day.year}"


def reporting_quarters(today: date) -> list[Period]:
    """Q1 2025 through Q4 of the next calendar (fiscal) year after ``today``."""
    return Period.list(OUTPUT_START, QUARTER, date(today.year + 1, 12, 31))


def last_period(periods: Iterable[Period]) -> Period:
    last: Period | None = None
    for period in periods:
        last = period
    if last is None:
        raise RuntimeError("expected at least one period")
    return last


@cache
def load_reported_quarters(path: Path = CSV_PATH) -> tuple[ReportedQuarter, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            ReportedQuarter(
                period=parse_quarter_label(row["quarter"]),
                passenger_non_loyalty=float(row["passenger_non_loyalty"]),
                loyalty_air_transport=float(row["loyalty_air_transport"]),
                ancillary=float(row["ancillary"]),
                freight=float(row["freight"]),
                other=float(row["other"]),
            )
            for row in DictReader(handle)
        ]
    if not rows:
        raise RuntimeError(f"no revenue rows in {path}")
    return tuple(rows)


def qtd_windows(current: Period, last_observation: date) -> tuple[Period, Period]:
    """Current-quarter QTD and the same elapsed window of the prior quarter."""
    if last_observation <= current.start or last_observation > current.end:
        raise ValueError(f"last TSA date {last_observation.isoformat()} is not inside {current}")
    qtd = Period(current.start, last_observation)
    prior = current.shift(-QUARTER)
    return qtd, Period(prior.start, prior.start + (last_observation - current.start))


def nowcast_spec(ctx: Context, today: date) -> NowcastSpec | None:
    current = quarter_containing(today)
    if any(row.period == current for row in load_reported_quarters()):
        return None
    last_tsa = last_period(ctx.get(tsa_passengers.keys()))
    qtd, prior_qtd = qtd_windows(current, last_tsa.end)
    return NowcastSpec(current, current.shift(-QUARTER), qtd, prior_qtd)


def _line_item(
    name: str,
    getter: LineGetter,
    *,
    scale_current_with_tsa: bool,
) -> PeriodSeries[Maybe[float]]:
    @PeriodSeries.define(name, ACCRUE)
    def series() -> CellStream[Period, float]:
        reported = load_reported_quarters()
        last_reported = reported[-1].period
        current = last_reported.from_end(QUARTER)
        forecast_end = date(as_of_date().year + 1, 12, 31)

        tsa_days = yield from get(tsa_passengers.keys())
        last_tsa = last_period(tsa_days)
        qtd, prior_qtd = qtd_windows(current, last_tsa.end)

        for row in reported:
            yield row.period, getter(row)

        def current_factory(
            period: Period = current,
            qtd_period: Period = qtd,
            prior_qtd_period: Period = prior_qtd,
        ) -> Step[float]:
            prior = yield from get_at(series, period.shift(-QUARTER))
            if isna(prior):
                raise ValueError(f"missing {name} for {period.shift(-QUARTER)}")
            if not scale_current_with_tsa:
                return prior
            current_tsa = yield from get_at(tsa_passengers, qtd_period)
            prior_tsa = yield from get_at(tsa_passengers, prior_qtd_period)
            if isna(current_tsa) or isna(prior_tsa):
                raise ValueError(f"missing TSA QTD volumes for {name} at {period}")
            if prior_tsa == 0.0:
                raise ValueError(f"prior-quarter TSA QTD is zero for {name} at {period}")
            return prior * (current_tsa / prior_tsa)

        yield current, current_factory

        for key in Period.seq(current.end, QUARTER, forecast_end):

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
    "Passenger non-loyalty",
    lambda row: row.passenger_non_loyalty,
    scale_current_with_tsa=True,
)
loyalty_air_transport = _line_item(
    "Loyalty – air transport",
    lambda row: row.loyalty_air_transport,
    scale_current_with_tsa=True,
)
ancillary = _line_item(
    "Ancillary",
    lambda row: row.ancillary,
    scale_current_with_tsa=True,
)
freight = _line_item(
    "Freight",
    lambda row: row.freight,
    scale_current_with_tsa=False,
)
other = _line_item(
    "Other",
    lambda row: row.other,
    scale_current_with_tsa=False,
)

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
                [
                    passenger_non_loyalty,
                    loyalty_air_transport,
                    ancillary,
                ],
            ),
            freight,
            other,
        ],
    )
)
