# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Common ``QueryFn`` helpers for series."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

from orcaset.maybe import Maybe, Na
from orcaset.period import Period
from orcaset.rule import RuleBase, Step, get
from orcaset.series import Key, QueryFn

type DayCount = Callable[[date, date], float]
"""Maps an ordered date pair to a length (year fraction, days, …)."""


def exact[K: Key, V](q: K, cells: Iterable[tuple[K, RuleBase[V]]]) -> Step[Maybe[V]]:
    """Point lookup: return the cell at ``q``, or ``Na`` if missing.

    Scans an ascending key stream; overlapping but non-equal keys are skipped
    without forcing. Query key and domain key are the same type. Prefer
    ``exact_or(default)`` when misses should be a concrete value.
    """
    for k, cell in cells:
        if k < q:
            continue
        if q < k:
            break
        if k == q:
            return (yield from get(cell))
    return Na


def exact_or[K: Key, V](default: V) -> QueryFn[K, K, V, V]:
    """Like ``exact``, but answer ``default`` instead of ``Na`` on a miss."""

    def query(q: K, cells: Iterable[tuple[K, RuleBase[V]]]) -> Step[V]:
        for k, cell in cells:
            if k < q:
                continue
            if q < k:
                break
            if k == q:
                return (yield from get(cell))
        return default

    return query


def last[K: Key, V](q: K, cells: Iterable[tuple[K, RuleBase[V]]]) -> Step[Maybe[V]]:
    """As-of lookup: return the latest cell at or before ``q``, or ``Na``.

    Scans an ascending key stream without forcing cells that are strictly
    before a later candidate. Stops at the first key strictly after ``q``.
    Query key and domain key are the same type.
    """
    pending: RuleBase[V] | None = None
    for k, cell in cells:
        if k < q:
            pending = cell
            continue
        if q < k:
            break
        if k == q:
            return (yield from get(cell))
    if pending is None:
        return Na
    return (yield from get(pending))


def accrual(yf: DayCount) -> QueryFn[Period, Period, float, Maybe[float]]:
    """Build a period query that weights overlapping cells by ``yf``.

    Exact key hits return the cell value unchanged. Otherwise each overlapping
    cell contributes ``value * yf(overlap) / yf(cell)``. ``yf`` is any
    ``(date, date) -> float`` measure — e.g. ``YF.act360``, ``YF.thirty360``,
    ``YF.cmonthly``, or ``lambda a, b: (b - a).days``. Prefer ``accrual_or``
    when misses should be a concrete value.
    """

    def query(q: Period, cells: Iterable[tuple[Period, RuleBase[float]]]) -> Step[Maybe[float]]:
        total = 0.0
        hit = False
        for k, cell in cells:
            if k < q:
                continue
            if q < k:
                break
            value = yield from get(cell)
            if k == q:
                return value
            overlap_start = max(k.start, q.start)
            overlap_end = min(k.end, q.end)
            total += value * (yf(overlap_start, overlap_end) / yf(k.start, k.end))
            hit = True
        return total if hit else Na

    return query


def accrual_or(yf: DayCount, default: float) -> QueryFn[Period, Period, float, float]:
    """Like ``accrual(yf)``, but answer ``default`` instead of ``Na`` on a miss."""

    def query(q: Period, cells: Iterable[tuple[Period, RuleBase[float]]]) -> Step[float]:
        total = 0.0
        hit = False
        for k, cell in cells:
            if k < q:
                continue
            if q < k:
                break
            value = yield from get(cell)
            if k == q:
                return value
            overlap_start = max(k.start, q.start)
            overlap_end = min(k.end, q.end)
            total += value * (yf(overlap_start, overlap_end) / yf(k.start, k.end))
            hit = True
        return total if hit else default

    return query


def covered(q: Period, cells: Iterable[tuple[Period, RuleBase[float]]]) -> Step[Maybe[float]]:
    """Sum cells that exactly tile ``q``; ``Na`` on any gap or partial overlap.

    Unlike ``exact``, a query that is the union of adjacent cells is answered.
    Unlike ``accrual``, a query that cuts through a cell is ``Na``.
    """
    total = 0.0
    expected_start = q.start
    covered_end: date | None = None
    for k, cell in cells:
        if k < q:
            continue
        if q < k:
            break
        if k.start != expected_start or k.end > q.end:
            return Na
        value = yield from get(cell)
        total += value
        expected_start = k.end
        covered_end = k.end
    if covered_end != q.end:
        return Na
    return total
