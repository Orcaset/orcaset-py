# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Query helpers for series."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import cast

from orcaset import maybe
from orcaset.maybe import Maybe, Na, NaType, isna
from orcaset.period import Period
from orcaset.rule import Effect, Rule, get
from orcaset.series import Chain, Key, QueryFn

__all__ = [
    "DayCount",
    "accrue",
    "accrue_drop",
    "avg",
    "avg_drop",
    "avg_fill",
    "covered",
    "exact",
    "exact_or",
    "filled",
    "last",
    "last_or",
]

type DayCount = Callable[[date, date], float]
"""Maps an ordered date pair to a length (year fraction, days, …)."""


def exact[K: Key, V](q: K, cells: Chain[K, V]) -> Effect[Maybe[V]]:
    """Return the cell exactly at ``q``, or ``Na`` if it is absent."""
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            node = yield from get(node.tail)
        elif q < node.key:
            return Na
        elif node.key == q:
            return (yield from get(node.value))
        else:
            return Na
    return Na


def last[K: Key, V](q: K, cells: Chain[K, V]) -> Effect[Maybe[V]]:
    """Return the latest strictly prior or exactly matching cell, or ``Na``."""
    pending: Rule[V] | None = None
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            pending = node.value
            node = yield from get(node.tail)
        elif node.key == q:
            return (yield from get(node.value))
        elif q < node.key:
            break
        else:
            break
    if pending is None:
        return Na
    return (yield from get(pending))


def exact_or[K: Key, V](default: V) -> QueryFn[K, V, V]:
    """Build an exact-match query that returns ``default`` on a miss."""

    def query(q: K, cells: Chain[K, V]) -> Effect[V]:
        return maybe.value_or((yield from exact(q, cells)), default)

    return query


def last_or[K: Key, V](default: V) -> QueryFn[K, V, V]:
    """Build a latest-value query that returns ``default`` before the first cell."""

    def query(q: K, cells: Chain[K, V]) -> Effect[V]:
        return maybe.value_or((yield from last(q, cells)), default)

    return query


def filled(
    fn: Callable[[Sequence[float]], float],
    fill: Maybe[float] = Na,
) -> Callable[[Sequence[Maybe[float]]], Maybe[float]]:
    """Lift a float fold to ``Maybe`` answers with a fill policy.

    Each ``Na`` is replaced by ``fill`` before ``fn`` runs; when ``fill`` is
    itself ``Na`` (the default) any ``Na`` makes the result ``Na``.
    """

    def apply(values: Sequence[Maybe[float]]) -> Maybe[float]:
        present: list[float] = []
        for value in values:
            if isna(value):
                if isna(fill):
                    return Na
                value = fill
            present.append(value)
        return fn(present)

    return apply


def accrue[V: float | NaType](yf: DayCount) -> QueryFn[Period, V, Maybe[float]]:
    """Accrue cells over a query that the cells must cover.

    Each cell contributes ``value * yf(overlap) / yf(cell)``; a cell wholly
    inside the query contributes its full value, and a zero-``yf`` cell (e.g.
    ``YF.thirty360`` over Jan 30 - Jan 31) is prorated by actual days. A cell
    may extend past the query. ``Na`` when any date in the query falls outside
    the cells — before the first, after the last, or in a gap — or when an
    overlapping cell is ``Na``.
    """

    def query(q: Period, cells: Chain[Period, V]) -> Effect[Maybe[float]]:
        return (yield from _accrue(q, cells, yf, strict=True))

    return query


def accrue_drop[V: float | NaType](yf: DayCount) -> QueryFn[Period, V, Maybe[float]]:
    """Accrue the covered part of the query and ignore the rest.

    Time before, after, or between cells adds nothing, so a query with no
    overlapping cell is ``0.0``. An ``Na`` cell still makes the result ``Na``.
    """

    def query(q: Period, cells: Chain[Period, V]) -> Effect[Maybe[float]]:
        return (yield from _accrue(q, cells, yf, strict=False))

    return query


def avg[V: float | NaType](yf: DayCount) -> QueryFn[Period, V, Maybe[float]]:
    """Average cell values over a query that the cells must cover.

    Each covering cell is weighted by ``yf`` of its overlap with the query.
    ``Na`` when any date in the query falls outside the cells — before the
    first, after the last, or in a gap — or when an overlapping cell is ``Na``.
    When ``yf`` measures the whole query as zero (e.g. ``YF.thirty360`` over
    Jan 30 - Jan 31), segments are weighted by actual days instead.
    """

    def query(q: Period, cells: Chain[Period, V]) -> Effect[Maybe[float]]:
        return (yield from _avg(q, cells, yf, strict=True))

    return query


def avg_drop[V: float | NaType](yf: DayCount) -> QueryFn[Period, V, Maybe[float]]:
    """Average the covered part of the query and ignore the rest.

    Time before, after, or between cells is left out of the weights. An
    ``Na`` cell still makes the result ``Na``. A query with no overlapping
    cell is ``Na``.
    """

    def query(q: Period, cells: Chain[Period, V]) -> Effect[Maybe[float]]:
        return (yield from _avg(q, cells, yf, strict=False))

    return query


def avg_fill[V: float | NaType](
    yf: DayCount, fill: float
) -> QueryFn[Period, V, Maybe[float]]:
    """Fill time the cells don't cover with the level ``fill``, then average.

    Uncovered time contributes ``fill``, weighted by ``yf``, so the average
    spans the whole query. A complete miss is ``fill``. An ``Na`` cell still
    makes the result ``Na``. When ``yf`` measures the whole query as zero,
    segments are weighted by actual days instead.
    """

    def query(q: Period, cells: Chain[Period, V]) -> Effect[Maybe[float]]:
        return (yield from _avg(q, cells, yf, strict=False, fill=fill))

    return query


def _overlaps[V](
    q: Period, cells: Chain[Period, V], *, strict: bool
) -> Effect[list[tuple[Period, Period, Rule[V]]] | None]:
    """List ``(cell, overlap, value)`` for each cell overlapping ``q``, in order.

    Values are left unforced so a strict miss costs no cell values. ``None``
    when ``strict`` and any date in ``q`` falls outside the cells.
    """
    found: list[tuple[Period, Period, Rule[V]]] = []
    cursor = q.start
    node = yield from get(cells)
    while node is not None:
        k = node.key
        if k < q:
            node = yield from get(node.tail)
            continue
        if q < k:
            break
        if strict and cursor < k.start:
            return None
        overlap = Period(max(k.start, q.start), min(k.end, q.end))
        found.append((k, overlap, node.value))
        cursor = overlap.end
        if k.end >= q.end:
            break
        node = yield from get(node.tail)
    if strict and cursor < q.end:
        return None
    return found


def _avg[V: float | NaType](
    q: Period,
    cells: Chain[Period, V],
    yf: DayCount,
    *,
    strict: bool,
    fill: float | None = None,
) -> Effect[Maybe[float]]:
    """Average over ``q``; uncovered time is ``Na`` if ``strict``, else ``fill`` or dropped."""
    overlaps = yield from _overlaps(q, cells, strict=strict)
    if overlaps is None:
        return Na
    segments: list[tuple[float, Period]] = []
    cursor = q.start
    for _, overlap, rule in overlaps:
        if fill is not None and cursor < overlap.start:
            segments.append((fill, Period(cursor, overlap.start)))
        value = yield from get(rule)
        if isna(value):
            return Na
        segments.append((cast(float, value), overlap))
        cursor = overlap.end
    if fill is not None and cursor < q.end:
        segments.append((fill, Period(cursor, q.end)))
    if not segments:
        return Na
    # A zero-measure query under ``yf`` (e.g. thirty360 over 1/30-1/31) still
    # averages the values it covers, weighted by actual days instead.
    weights = [yf(p.start, p.end) for _, p in segments]
    if not sum(weights):
        weights = [float((p.end - p.start).days) for _, p in segments]
    weighted = sum(amount * w for (amount, _), w in zip(segments, weights))
    return weighted / sum(weights)


def _accrue[V: float | NaType](
    q: Period,
    cells: Chain[Period, V],
    yf: DayCount,
    *,
    strict: bool,
) -> Effect[Maybe[float]]:
    """Accrue over ``q``; uncovered time is ``Na`` if ``strict``, else adds nothing."""
    overlaps = yield from _overlaps(q, cells, strict=strict)
    if overlaps is None:
        return Na
    total = 0.0
    for cell, overlap, rule in overlaps:
        value = yield from get(rule)
        if isna(value):
            return Na
        total += cast(float, value) * _share(cell, overlap, yf)
    return total


def _share(cell: Period, overlap: Period, yf: DayCount) -> float:
    """Fraction of ``cell`` that ``overlap`` covers, measured by ``yf``."""
    if overlap == cell:
        return 1.0
    cell_len = yf(cell.start, cell.end)
    if cell_len:
        return yf(overlap.start, overlap.end) / cell_len
    # Zero-measure cell under ``yf`` (e.g. thirty360 over 1/30-1/31): prorate
    # by actual days instead of 0/0.
    return (overlap.end - overlap.start).days / (cell.end - cell.start).days


def covered(q: Period, cells: Chain[Period, Maybe[float]]) -> Effect[Maybe[float]]:
    """Sum one or more cells that exactly tile ``q`` or return ``Na`` on any gap or partial overlap.

    Unlike ``exact``, a query that is the union of adjacent cells is answered.
    Unlike ``accrue``, a query that cuts through a cell is ``Na``. Any ``Na`` among the tiling cells is ``Na``.
    """
    overlaps = yield from _overlaps(q, cells, strict=True)
    # Strict coverage already rules out gaps, so only the end cells can cut q.
    if overlaps is None or overlaps[0][0].start != q.start or overlaps[-1][0].end != q.end:
        return Na
    total = 0.0
    for _, _, rule in overlaps:
        value = yield from get(rule)
        if isna(value):
            return Na
        total += value
    return total
