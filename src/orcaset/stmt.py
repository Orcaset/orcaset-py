# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .context import Context
from .period import Period
from .point import PointSeriesDef
from .span import KeyedSpanSeries, SpanSeriesDef


type StmtSeries = SpanSeriesDef | PointSeriesDef
type StmtItem = StmtSeries | KeyedSpanSeries | Total | Group
type StmtValue = PeriodValue | DateValue


@dataclass(slots=True)
class PeriodValue:
    period: Period
    value: float | None


@dataclass(slots=True)
class DateValue:
    date: date
    value: float | None


@dataclass(slots=True)
class LineRow:
    name: str
    series: StmtSeries
    values: tuple[StmtValue, ...]


@dataclass(slots=True)
class TotalRow:
    name: str
    series: StmtSeries
    values: tuple[StmtValue, ...]
    children: tuple[StmtRow, ...]


@dataclass(slots=True)
class GroupRow:
    children: tuple[StmtRow, ...]


type StmtRow = LineRow | TotalRow | GroupRow


@dataclass(slots=True)
class StatementResult:
    rows: tuple[StmtRow, ...]
    periods: tuple[Period, ...]
    dates: tuple[date, ...]


@dataclass(slots=True)
class Total:
    series: StmtSeries
    items: tuple[StmtItem, ...] = ()

    def __init__(self, series: StmtSeries, items: Sequence[StmtItem]) -> None:
        self.series = series
        self.items = tuple(items)


@dataclass(slots=True)
class Group:
    items: tuple[StmtItem, ...]

    def __init__(self, items: Sequence[StmtItem]) -> None:
        self.items = tuple(items)


class Stmt:
    __slots__ = ("items",)

    def __init__(self, *items: StmtItem) -> None:
        self.items = tuple(items)

    def values(
        self,
        ctx: Context,
        periods: Sequence[Period],
    ) -> StatementResult:
        return self.values_for_periods(ctx, periods)

    def values_for_periods(
        self,
        ctx: Context,
        periods: Sequence[Period],
    ) -> StatementResult:
        period_tuple = tuple(periods)
        date_tuple = _period_boundaries(period_tuple)
        rows = tuple(_period_row(ctx, item, period_tuple, date_tuple) for item in self.items)
        return StatementResult(rows=rows, periods=period_tuple, dates=date_tuple)

    def values_for_dates(
        self,
        ctx: Context,
        dates: Sequence[date],
    ) -> StatementResult:
        date_tuple = tuple(dict.fromkeys(dates))
        rows = tuple(_date_row(ctx, item, date_tuple) for item in self.items)
        return StatementResult(rows=rows, periods=(), dates=date_tuple)


def _period_row(
    ctx: Context,
    item: StmtItem,
    periods: Sequence[Period],
    dates: Sequence[date],
) -> StmtRow:
    if isinstance(item, KeyedSpanSeries):
        return GroupRow(
            children=tuple(
                _period_row(ctx, series, periods, dates) for _, series in item.items(ctx, periods)
            )
        )

    if isinstance(item, Total):
        return TotalRow(
            name=item.series.label,
            series=item.series,
            values=_series_period_values(ctx, item.series, periods, dates),
            children=tuple(_period_row(ctx, child, periods, dates) for child in item.items),
        )

    if isinstance(item, Group):
        return GroupRow(
            children=tuple(_period_row(ctx, child, periods, dates) for child in item.items),
        )

    return LineRow(
        name=item.label,
        series=item,
        values=_series_period_values(ctx, item, periods, dates),
    )


def _date_row(
    ctx: Context,
    item: StmtItem,
    dates: Sequence[date],
) -> StmtRow:
    if isinstance(item, KeyedSpanSeries):
        raise TypeError("Keyed span series can only be rendered for period queries")

    if isinstance(item, Total):
        return TotalRow(
            name=item.series.label,
            series=item.series,
            values=_series_date_values(ctx, item.series, dates),
            children=tuple(_date_row(ctx, child, dates) for child in item.items),
        )

    if isinstance(item, Group):
        return GroupRow(children=tuple(_date_row(ctx, child, dates) for child in item.items))

    return LineRow(
        name=item.label,
        series=item,
        values=_series_date_values(ctx, item, dates),
    )


def _series_period_values(
    ctx: Context,
    series: StmtSeries,
    periods: Sequence[Period],
    dates: Sequence[date],
) -> tuple[StmtValue, ...]:
    if isinstance(series, SpanSeriesDef):
        return _span_values(ctx, series, periods)
    return _point_values(ctx, series, dates)


def _series_date_values(
    ctx: Context,
    series: StmtSeries,
    dates: Sequence[date],
) -> tuple[DateValue, ...]:
    if isinstance(series, SpanSeriesDef):
        return tuple(DateValue(dt, None) for dt in dates)
    return _point_values(ctx, series, dates)


def _span_values(
    ctx: Context,
    series: SpanSeriesDef,
    periods: Sequence[Period],
) -> tuple[PeriodValue, ...]:
    return tuple(PeriodValue(period, series.value(ctx, period).eval()) for period in periods)


def _point_values(
    ctx: Context,
    series: PointSeriesDef,
    dates: Sequence[date],
) -> tuple[DateValue, ...]:
    return tuple(DateValue(dt, series.query(ctx, dt).eval(ctx)) for dt in dates)


def _period_boundaries(periods: Sequence[Period]) -> tuple[date, ...]:
    return tuple(sorted({dt for period in periods for dt in (period.start, period.end)}))
