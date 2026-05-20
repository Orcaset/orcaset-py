# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass

from .cell import Span
from .context import Context
from .period import Period
from .series import SpanSeries, SpanSeriesFamily


type StmtReducer = Callable[[list[Span]], float | None]
type StmtItem = type[SpanSeries] | type[SpanSeriesFamily] | Total | Group


@dataclass
class LineRow:
    name: str
    series: type[SpanSeries]
    values: tuple[float | None, ...]


@dataclass
class TotalRow:
    name: str
    series: type[SpanSeries]
    values: tuple[float | None, ...]
    children: tuple[StmtRow, ...]


@dataclass
class GroupRow:
    children: tuple[StmtRow, ...]


@dataclass
class FamilyRow:
    name: str
    family: type[SpanSeriesFamily]
    children: tuple["FamilyLineRow", ...]


@dataclass
class FamilyLineRow:
    name: str
    family: type[SpanSeriesFamily]
    key: Hashable
    values: tuple[float | None, ...]


type StmtRow = LineRow | TotalRow | GroupRow | FamilyRow | FamilyLineRow


@dataclass
class Total:
    series: type[SpanSeries]
    items: tuple[StmtItem, ...] = ()

    def __init__(self, series: type[SpanSeries], items: Sequence[StmtItem]) -> None:
        self.series = series
        self.items = tuple(items)


@dataclass
class Group:
    items: tuple[StmtItem, ...]

    def __init__(self, items: Sequence[StmtItem]) -> None:
        self.items = tuple(items)


class Stmt:
    def __init__(self, *items: StmtItem) -> None:
        self.items = tuple(items)

    def values(
        self,
        ctx: Context,
        periods: Sequence[Period],
        reducer: StmtReducer | None = None,
    ) -> list[StmtRow]:
        reduce = reducer or _single_value
        return [_row(ctx, item, periods, reduce) for item in self.items]


def _row(
    ctx: Context,
    item: StmtItem,
    periods: Sequence[Period],
    reducer: StmtReducer,
) -> StmtRow:
    if isinstance(item, Total):
        return TotalRow(
            name=item.series.display_name(),
            series=item.series,
            values=_values(ctx, item.series, periods, reducer),
            children=tuple(_row(ctx, child, periods, reducer) for child in item.items),
        )

    if isinstance(item, Group):
        return GroupRow(
            children=tuple(_row(ctx, child, periods, reducer) for child in item.items),
        )

    if issubclass(item, SpanSeriesFamily):
        family_type = item
        return _family_row(ctx, family_type, periods, reducer)

    series_type = item

    return LineRow(
        name=series_type.display_name(),
        series=series_type,
        values=_values(ctx, series_type, periods, reducer),
    )


def _family_row(
    ctx: Context,
    family_type: type[SpanSeriesFamily],
    periods: Sequence[Period],
    reducer: StmtReducer,
) -> StmtRow:
    family = ctx.get(family_type)
    results = tuple(family.query(period).eval() for period in periods)
    keys = _family_keys(results)

    return FamilyRow(
        name=family_type.display_name(),
        children=tuple(
            FamilyLineRow(
                name=family.key_label(key),
                family=family_type,
                key=key,
                values=_family_values(results, key, reducer),
            )
            for key in keys
        ),
        family=family_type,
    )


def _family_keys(results: Sequence[Mapping[Hashable, Sequence[Span]]]) -> tuple[Hashable, ...]:
    keys: list[Hashable] = []
    seen: set[Hashable] = set()
    for result in results:
        for key in result:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return tuple(keys)


def _family_values(
    results: Sequence[Mapping[Hashable, Sequence[Span]]],
    key: Hashable,
    reducer: StmtReducer,
) -> tuple[float | None, ...]:
    return tuple(None if key not in result else reducer(list(result[key])) for result in results)


def _values(
    ctx: Context,
    series_type: type[SpanSeries],
    periods: Sequence[Period],
    reducer: StmtReducer,
) -> tuple[float | None, ...]:
    series = ctx.get(series_type)
    return tuple(reducer(series.query(period).eval()) for period in periods)


def _single_value(spans: list[Span]) -> float | None:
    if len(spans) != 1:
        raise ValueError(
            "Stmt.values requires a reducer when a period query returns multiple spans"
        )
    span = spans[0]
    if span._ctx is None:
        raise RuntimeError("Stmt.values expected spans returned by SpanSeries.query")
    return span.eval(span._ctx)
