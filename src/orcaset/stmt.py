# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Statement views over period- and date-keyed series.

Build a ``Stmt`` from line items, ``Total``s, and ``Group``s, then evaluate with
``values`` at any mix of periods and dates.

Every row holds one ``StmtValue`` per requested key, in key order, and each
value names its ``key``. At a ``Period`` key, period-keyed series are queried
at the period and date-keyed series at the period's end. At a ``date`` key,
date-keyed series are queried at the date and period-keyed series are not
queried. Periods need not be sorted, contiguous, or disjoint. Each value keeps
the series, the key it was queried at, and the model value unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from orcaset.context import Context
from orcaset.maybe import Na
from orcaset.period import Period
from orcaset.series import Series

__all__ = [
    "Group",
    "GroupRow",
    "LineRow",
    "StatementResult",
    "Stmt",
    "StmtItem",
    "StmtKey",
    "StmtRow",
    "StmtSeries",
    "StmtValue",
    "Total",
    "TotalRow",
]

type StmtSeries = Series[Any, Any, Any]
type StmtItem = StmtSeries | Total | Group
type StmtKey = Period | date
type _KeyKind = Literal["period", "date", "empty"]


@dataclass(slots=True)
class StmtValue:
    """
    One statement cell: ``series`` evaluated for the column ``key``.

    ``query`` is the key the series was actually queried at: ``key`` itself, a
    period's end for a date-keyed series, or ``None`` when a period-keyed series
    is not queried at a date column. ``value`` is the model value unchanged, so
    units and citations survive; it is ``Na`` on a miss or when not queried.
    When ``query`` is set, ``ctx.dependencies(series, query)`` traces where the
    value came from.
    """

    key: StmtKey
    series: StmtSeries
    query: StmtKey | None
    value: object


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
    label: str | None
    children: tuple[StmtRow, ...]


type StmtRow = LineRow | TotalRow | GroupRow


@dataclass(slots=True)
class StatementResult:
    """Resolved statement rows and the keys they were evaluated at, in input order."""

    rows: tuple[StmtRow, ...]
    keys: tuple[StmtKey, ...]

    @property
    def periods(self) -> tuple[Period, ...]:
        return tuple(key for key in self.keys if isinstance(key, Period))

    @property
    def dates(self) -> tuple[date, ...]:
        return tuple(key for key in self.keys if not isinstance(key, Period))


@dataclass(slots=True)
class Total:
    series: StmtSeries
    items: tuple[StmtItem, ...]

    def __init__(self, series: StmtSeries, items: Sequence[StmtItem]) -> None:
        self.series = series
        self.items = tuple(items)


@dataclass(slots=True)
class Group:
    items: tuple[StmtItem, ...]
    label: str | None = None

    def __init__(self, *items: StmtItem, label: str | None = None) -> None:
        self.items = tuple(items)
        self.label = label


class Stmt:
    __slots__ = ("items",)

    def __init__(self, *items: StmtItem) -> None:
        self.items = tuple(items)

    def values(
        self,
        ctx: Context,
        keys: Sequence[StmtKey],
    ) -> StatementResult:
        """
        Evaluate the statement with one value per key, in the order given.

        Each key is a ``Period`` or a ``date``, and the two may be mixed. At a
        period, period-keyed series answer at the period and date-keyed series
        answer at the period's end. At a date, date-keyed series answer at the
        date and period-keyed series are not queried (``query`` is ``None``
        and ``value`` is ``Na``). Keys are not sorted or
        deduplicated; periods may have gaps, overlap, or nest.
        """
        key_tuple = tuple(keys)
        rows = tuple(_row(ctx, item, key_tuple) for item in self.items)
        return StatementResult(rows=rows, keys=key_tuple)


def _row(
    ctx: Context,
    item: StmtItem,
    keys: Sequence[StmtKey],
) -> StmtRow:
    match item:
        case Total():
            return TotalRow(
                name=item.series.name,
                series=item.series,
                values=_series_values(ctx, item.series, keys),
                children=tuple(_row(ctx, child, keys) for child in item.items),
            )
        case Group():
            return GroupRow(
                label=item.label,
                children=tuple(_row(ctx, child, keys) for child in item.items),
            )
        case Series():
            return LineRow(
                name=item.name,
                series=item,
                values=_series_values(ctx, item, keys),
            )
        case _:
            raise TypeError(f"statement items must be Series, Total, or Group, got {type(item)!r}")


def _series_values(
    ctx: Context,
    series: StmtSeries,
    keys: Sequence[StmtKey],
) -> tuple[StmtValue, ...]:
    kind = _key_kind(ctx, series)
    return tuple(_key_value(ctx, series, kind, key) for key in keys)


def _key_value(ctx: Context, series: StmtSeries, kind: _KeyKind, key: StmtKey) -> StmtValue:
    query = _query_key(kind, key)
    value = Na if query is None else ctx.get_at(series, query)
    return StmtValue(key=key, series=series, query=query, value=value)


def _query_key(kind: _KeyKind, key: StmtKey) -> StmtKey | None:
    if isinstance(key, Period):
        # Date-keyed series report the closing value at the period's end.
        return key.end if kind == "date" else key
    return None if kind == "period" else key


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
