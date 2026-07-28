# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Construction helpers for common Period-keyed series.

Select/reduce are a matched pair; these factories are where the pairing
happens. Line items compose conventions inline instead of importing a class
per combination:

    revenue = flow("revenue", months, rev_at, yf=YF.cmonthly)
    rent = flow("rent", quarters, rent_at, yf=YF.cmonthly)  # quarter = 1/4 year
    accrual = flow("accrual", periods, acc_at, yf=YF.thirty360)
    balance = level("balance", months, bal_at, yf=YF.act360)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from orcaset.period import Period
from orcaset.rule import Rule
from orcaset.series import GridSeries, Keys, Maybe, Na, ReduceFn, ValueFn, isna
from orcaset.yf import YfType

# ---------- selects ----------


def overlapping(keys: Keys[Period], q: Period) -> Sequence[Period]:
    """Grid periods overlapping ``q``, ascending. Early-terminating scan."""
    out: list[Period] = []
    for k in keys:
        if k < q:
            continue
        if q < k:
            break
        out.append(k)
    return out


# ---------- reduces ----------


def prorated(yf: YfType) -> ReduceFn[Period, Period, float, Maybe[float]]:
    """Flow reduce: each cell contributes its value scaled by the ``yf``
    fraction of the cell that ``q`` overlaps.

    Policy: empty selection answers ``Na``; partial coverage (``q`` extends
    past the domain) sums the covered part.
    """

    def reduce(q: Period, items: Sequence[tuple[Period, Maybe[float]]]) -> Maybe[float]:
        total = 0.0
        hit = False
        for k, v in items:
            if isna(v):
                continue
            o = _overlap(k, q)
            total += v * (yf(o.start, o.end) / yf(k.start, k.end))
            hit = True
        return total if hit else Na

    return reduce


def time_weighted(yf: YfType) -> ReduceFn[Period, Period, float, Maybe[float]]:
    """Level reduce: value identity within a cell; across cells, the
    time-weighted average of cell values, weighted by overlap under ``yf``.

    Policy: empty selection or zero total weight answers ``Na``.
    """

    def reduce(q: Period, items: Sequence[tuple[Period, Maybe[float]]]) -> Maybe[float]:
        num = 0.0
        den = 0.0
        for k, v in items:
            if isna(v):
                continue
            o = _overlap(k, q)
            w = yf(o.start, o.end)
            num += v * w
            den += w
        return num / den if den else Na

    return reduce


def _overlap(k: Period, q: Period) -> Period:
    return Period(max(k.start, q.start), min(k.end, q.end))


# ---------- factories ----------

type _PeriodKeys = Rule[None, Keys[Period]] | Callable[[], Iterable[Period]]
type _FloatSeries = GridSeries[Period, Period, float, Maybe[float]]


def flow(
    name: str,
    keys: _PeriodKeys,
    value_at: ValueFn[Period, float],
    *,
    yf: YfType,
) -> _FloatSeries:
    """A flow line item: cell values are period totals, prorated across query
    boundaries by ``yf`` (the day-count/grid convention).
    """
    return GridSeries(name, keys, value_at, select=overlapping, reduce=prorated(yf))


def level(
    name: str,
    keys: _PeriodKeys,
    value_at: ValueFn[Period, float],
    *,
    yf: YfType,
) -> _FloatSeries:
    """A level line item: cell values are states, not totals; queries answer
    the time-weighted average over the overlapped cells.
    """
    return GridSeries(name, keys, value_at, select=overlapping, reduce=time_weighted(yf))
