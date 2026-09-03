# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Common ``QueryFn`` helpers for series."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from orcaset.maybe import Maybe, Na, isna, value_or
from orcaset.period import Period
from orcaset.rule import Rule, Step, get
from orcaset.series import Cells, Key, QueryFn

type DayCount = Callable[[date, date], float]
"""Maps an ordered date pair to a length (year fraction, days, …)."""


def exact[K: Key, V](q: K, cells: Cells[K, V]) -> Step[Maybe[V]]:
    """Return the cell exactly at ``q``, or ``Na`` if it is absent."""
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            node = yield from get(node.tail)
        elif q < node.key:
            return Na
        elif node.key == q:
            return (yield from get(node.cell))
        else:
            node = yield from get(node.tail)
    return Na


def last[K: Key, V](q: K, cells: Cells[K, V]) -> Step[Maybe[V]]:
    """Return the latest strictly prior or exactly matching cell, or ``Na``."""
    pending: Rule[V] | None = None
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            pending = node.cell
            node = yield from get(node.tail)
        elif node.key == q:
            return (yield from get(node.cell))
        elif q < node.key:
            break
        else:
            node = yield from get(node.tail)
    if pending is None:
        return Na
    return (yield from get(pending))


def exact_or[K: Key, V](default: V) -> QueryFn[K, V, V]:
    """Build an exact-match query that returns ``default`` on a miss."""

    def query(q: K, cells: Cells[K, V]) -> Step[V]:
        return value_or((yield from exact(q, cells)), default)

    return query


def last_or[K: Key, V](default: V) -> QueryFn[K, V, V]:
    """Build a latest-value query that returns ``default`` before the first cell."""

    def query(q: K, cells: Cells[K, V]) -> Step[V]:
        return value_or((yield from last(q, cells)), default)

    return query


def accrual(yf: DayCount) -> QueryFn[Period, Maybe[float], Maybe[float]]:
    """Build a period query that weights overlapping cells by ``yf``.

    An exact key hit returns the cell value unchanged. Otherwise each cell
    overlapping ``q`` contributes ``value * yf(overlap) / yf(cell)``. ``yf`` is
    any ``(date, date) -> float`` measure — e.g. ``YF.act360``,
    ``YF.thirty360``, ``YF.cmonthly``, or ``lambda a, b: (b - a).days``.

    ``Na`` when no cell overlaps ``q`` or when any overlapping cell is ``Na``.
    """

    def query(q: Period, cells: Cells[Period, Maybe[float]]) -> Step[Maybe[float]]:
        return (yield from _accrue(q, cells, yf))

    return query


def accrual_or(yf: DayCount, fill: float) -> QueryFn[Period, Maybe[float], float]:
    """Build an accrual query that replaces an ``Na`` answer with ``fill``."""

    def query(q: Period, cells: Cells[Period, Maybe[float]]) -> Step[float]:
        return value_or((yield from _accrue(q, cells, yf)), fill)

    return query


def _accrue(
    q: Period, cells: Cells[Period, Maybe[float]], yf: DayCount
) -> Step[Maybe[float]]:
    total = 0.0
    hit = False
    node = yield from get(cells)
    while node is not None:
        k = node.key
        if k < q:
            node = yield from get(node.tail)
            continue
        if q < k:
            break
        value = yield from get(node.cell)
        if k == q:
            return value
        if isna(value):
            return Na
        overlap_start = max(k.start, q.start)
        overlap_end = min(k.end, q.end)
        total += value * (yf(overlap_start, overlap_end) / yf(k.start, k.end))
        hit = True
        node = yield from get(node.tail)
    return total if hit else Na


def covered(q: Period, cells: Cells[Period, Maybe[float]]) -> Step[Maybe[float]]:
    """Sum cells that exactly tile ``q``; ``Na`` on any gap or partial overlap.

    Unlike ``exact``, a query that is the union of adjacent cells is answered.
    Unlike ``accrual``, a query that cuts through a cell is ``Na``. Any ``Na``
    among the tiling cells is ``Na``.
    """
    total = 0.0
    expected_start = q.start
    covered_end: date | None = None
    node = yield from get(cells)
    while node is not None:
        k = node.key
        if k < q:
            node = yield from get(node.tail)
            continue
        if q < k:
            break
        if k.start != expected_start or k.end > q.end:
            return Na
        value = yield from get(node.cell)
        if isna(value):
            return Na
        total += value
        expected_start = k.end
        covered_end = k.end
        node = yield from get(node.tail)
    if covered_end != q.end:
        return Na
    return total
