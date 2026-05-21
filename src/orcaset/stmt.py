# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .cell import Point
from .context import Context
from .period import Period
from .point import PointSeries
from .series import PointSeriesFamily, SpanSeriesFamily
from .span import SpanSeries


type StmtSeries = type[SpanSeries] | type[PointSeries]
type StmtFamily = type[SpanSeriesFamily] | type[PointSeriesFamily]
type StmtItem = StmtSeries | StmtFamily | Total | Group
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


@dataclass(slots=True)
class FamilyRow:
    name: str
    family: StmtFamily
    children: tuple["FamilyLineRow", ...]


@dataclass(slots=True)
class FamilyLineRow:
    name: str
    family: StmtFamily
    key: Hashable
    values: tuple[StmtValue, ...]


type StmtRow = LineRow | TotalRow | GroupRow | FamilyRow | FamilyLineRow


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
    if isinstance(item, Total):
        return TotalRow(
            name=item.series.display_name(),
            series=item.series,
            values=_series_period_values(ctx, item.series, periods, dates),
            children=tuple(_period_row(ctx, child, periods, dates) for child in item.items),
        )

    if isinstance(item, Group):
        return GroupRow(
            children=tuple(_period_row(ctx, child, periods, dates) for child in item.items),
        )

    if issubclass(item, SpanSeriesFamily):
        return _span_family_period_row(ctx, item, periods)

    if issubclass(item, PointSeriesFamily):
        return _point_family_period_row(ctx, item, dates)

    return LineRow(
        name=item.display_name(),
        series=item,
        values=_series_period_values(ctx, item, periods, dates),
    )


def _date_row(
    ctx: Context,
    item: StmtItem,
    dates: Sequence[date],
) -> StmtRow:
    if isinstance(item, Total):
        return TotalRow(
            name=item.series.display_name(),
            series=item.series,
            values=_series_date_values(ctx, item.series, dates),
            children=tuple(_date_row(ctx, child, dates) for child in item.items),
        )

    if isinstance(item, Group):
        return GroupRow(children=tuple(_date_row(ctx, child, dates) for child in item.items))

    if issubclass(item, SpanSeriesFamily):
        return FamilyRow(name=item.display_name(), family=item, children=())

    if issubclass(item, PointSeriesFamily):
        return _point_family_date_row(ctx, item, dates)

    return LineRow(
        name=item.display_name(),
        series=item,
        values=_series_date_values(ctx, item, dates),
    )


def _series_period_values(
    ctx: Context,
    series_type: StmtSeries,
    periods: Sequence[Period],
    dates: Sequence[date],
) -> tuple[StmtValue, ...]:
    if issubclass(series_type, SpanSeries):
        return _span_values(ctx, series_type, periods)
    return _point_values(ctx, series_type, dates)


def _series_date_values(
    ctx: Context,
    series_type: StmtSeries,
    dates: Sequence[date],
) -> tuple[DateValue, ...]:
    if issubclass(series_type, SpanSeries):
        return tuple(DateValue(dt, None) for dt in dates)
    return _point_values(ctx, series_type, dates)


def _span_family_period_row(
    ctx: Context,
    family_type: type[SpanSeriesFamily],
    periods: Sequence[Period],
) -> FamilyRow:
    family = ctx.get(family_type)
    results = tuple(family.value(period).eval() for period in periods)
    keys = _family_keys(results)

    return FamilyRow(
        name=family_type.display_name(),
        family=family_type,
        children=tuple(
            FamilyLineRow(
                name=family.key_label(key),
                family=family_type,
                key=key,
                values=_span_family_values(results, periods, key),
            )
            for key in keys
        ),
    )


def _point_family_period_row(
    ctx: Context,
    family_type: type[PointSeriesFamily],
    dates: Sequence[date],
) -> FamilyRow:
    return _point_family_date_row(ctx, family_type, dates)


def _point_family_date_row(
    ctx: Context,
    family_type: type[PointSeriesFamily],
    dates: Sequence[date],
) -> FamilyRow:
    family = ctx.get(family_type)
    results = tuple(family.query(dt).eval() for dt in dates)
    keys = _family_keys(results)

    return FamilyRow(
        name=family_type.display_name(),
        family=family_type,
        children=tuple(
            FamilyLineRow(
                name=family.key_label(key),
                family=family_type,
                key=key,
                values=_point_family_values(ctx, results, dates, key),
            )
            for key in keys
        ),
    )


def _family_keys(results: Sequence[Mapping[Hashable, object]]) -> tuple[Hashable, ...]:
    keys: list[Hashable] = []
    seen: set[Hashable] = set()
    for result in results:
        for key in result:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return tuple(keys)


def _span_family_values(
    results: Sequence[Mapping[Hashable, float | None]],
    periods: Sequence[Period],
    key: Hashable,
) -> tuple[PeriodValue, ...]:
    return tuple(
        PeriodValue(period, None if key not in result else result[key])
        for period, result in zip(periods, results, strict=True)
    )


def _point_family_values(
    ctx: Context,
    results: Sequence[Mapping[Hashable, Point]],
    dates: Sequence[date],
    key: Hashable,
) -> tuple[DateValue, ...]:
    return tuple(
        DateValue(dt, None if key not in result else result[key].eval(ctx))
        for dt, result in zip(dates, results, strict=True)
    )


def _span_values(
    ctx: Context,
    series_type: type[SpanSeries],
    periods: Sequence[Period],
) -> tuple[PeriodValue, ...]:
    series = ctx.get(series_type)
    return tuple(PeriodValue(period, series.value(period).eval()) for period in periods)


def _point_values(
    ctx: Context,
    series_type: type[PointSeries],
    dates: Sequence[date],
) -> tuple[DateValue, ...]:
    series = ctx.get(series_type)
    return tuple(DateValue(dt, series.query(dt).eval().eval(ctx)) for dt in dates)


def _period_boundaries(periods: Sequence[Period]) -> tuple[date, ...]:
    return tuple(sorted({dt for period in periods for dt in (period.start, period.end)}))
