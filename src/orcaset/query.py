# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Common ``QueryFn`` helpers for series."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

from orcaset.maybe import Maybe, Na
from orcaset.period import Period
from orcaset.rule import Rule, Step, get
from orcaset.series import Key, QueryFn

type DayCount = Callable[[date, date], float]
"""Maps an ordered date pair to a length (year fraction, days, …)."""


def exact[K: Key, V](q: K, cells: Iterable[tuple[K, Rule[V]]]) -> Step[Maybe[V]]:
    """Point lookup: return the cell at ``q``, or ``Na`` if missing.

    Scans an ascending key stream; overlapping but non-equal keys are skipped
    without forcing. Query key and domain key are the same type.
    """
    for k, cell in cells:
        if k < q:
            continue
        if q < k:
            break
        if k == q:
            return (yield from get(cell))
    return Na


def accrual(yf: DayCount) -> QueryFn[Period, Period, float, Maybe[float]]:
    """Build a period query that weights overlapping cells by ``yf``.

    Exact key hits return the cell value unchanged. Otherwise each overlapping
    cell contributes ``value * yf(overlap) / yf(cell)``. ``yf`` is any
    ``(date, date) -> float`` measure — e.g. ``YF.act360``, ``YF.thirty360``,
    ``YF.cmonthly``, or ``lambda a, b: (b - a).days``.
    """

    def query(q: Period, cells: Iterable[tuple[Period, Rule[float]]]) -> Step[Maybe[float]]:
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
