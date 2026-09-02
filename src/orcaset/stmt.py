# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Statement views over period- and date-keyed series.

Build a ``Stmt`` from line items, ``Total``s, and ``Group``s, then evaluate with
``values_for_periods`` / ``values_for_dates``. Period-keyed series answer at each
requested period; date-keyed series answer at period boundaries (or at the
requested dates). ``Na`` becomes ``None`` in the structured result so formatters
can treat misses uniformly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from orcaset.context import Context
from orcaset.maybe import isna
from orcaset.period import Period
from orcaset.series import Series

type StmtSeries = Series[Any, Any, Any]
type StmtItem = StmtSeries | Total | Group
type StmtValue = PeriodValue | DateValue
type _KeyKind = Literal["period", "date", "empty"]


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
    if isinstance(item, Total):
        return TotalRow(
            name=item.series.name,
            series=item.series,
            values=_series_period_values(ctx, item.series, periods, dates),
            children=tuple(_period_row(ctx, child, periods, dates) for child in item.items),
        )

    if isinstance(item, Group):
        return GroupRow(
            children=tuple(_period_row(ctx, child, periods, dates) for child in item.items),
        )

    return LineRow(
        name=item.name,
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
            name=item.series.name,
            series=item.series,
            values=_series_date_values(ctx, item.series, dates),
            children=tuple(_date_row(ctx, child, dates) for child in item.items),
        )

    if isinstance(item, Group):
        return GroupRow(children=tuple(_date_row(ctx, child, dates) for child in item.items))

    return LineRow(
        name=item.name,
        series=item,
        values=_series_date_values(ctx, item, dates),
    )


def _series_period_values(
    ctx: Context,
    series: StmtSeries,
    periods: Sequence[Period],
    dates: Sequence[date],
) -> tuple[StmtValue, ...]:
    kind = _key_kind(ctx, series)
    if kind == "date":
        return _date_series_values(ctx, series, dates)
    # Period-keyed (or empty) series answer at each requested period.
    return tuple(
        PeriodValue(period, _optional_float(ctx.get_at(series, period))) for period in periods
    )


def _series_date_values(
    ctx: Context,
    series: StmtSeries,
    dates: Sequence[date],
) -> tuple[DateValue, ...]:
    kind = _key_kind(ctx, series)
    if kind == "period":
        return tuple(DateValue(dt, None) for dt in dates)
    return _date_series_values(ctx, series, dates)


def _date_series_values(
    ctx: Context,
    series: StmtSeries,
    dates: Sequence[date],
) -> tuple[DateValue, ...]:
    return tuple(DateValue(dt, _optional_float(ctx.get_at(series, dt))) for dt in dates)


def _key_kind(ctx: Context, series: StmtSeries) -> _KeyKind:
    node = ctx.get(series.cells)
    if node is None:
        return "empty"
    key = node.key
    if isinstance(key, Period):
        return "period"
    if isinstance(key, date):
        return "date"
    raise TypeError(
        f"statement series {series.name!r} must be keyed by Period or date, got {type(key)!r}"
    )


def _optional_float(value: object) -> float | None:
    if isna(value):
        return None
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def _period_boundaries(periods: Sequence[Period]) -> tuple[date, ...]:
    return tuple(sorted({dt for period in periods for dt in (period.start, period.end)}))
