# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Select and reduce conventions for :class:`~orcaset.series.Series`.

A convention pair defines how a series answers queries: ``select`` narrows
the ordered cell stream to the (possibly clipped) ``(key, cell)`` pairs
relevant to a query, and ``reduce`` collapses those pairs to one value. Both
are pure: they may construct nodes as data but never evaluate them, and they
preserve node identity on trivial paths so shared cells stay shared graph
nodes.

Presets:

- :func:`flow` — ``Period``-keyed flow line items: cells overlapping a query
  window are prorated by day count and summed; uncovered time contributes
  zero.
- :func:`keyed` — exact-keyed line items: the query is the key and exactly
  one cell answers it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .f import F, Pure
from .period import Period
from .series import Reduce, ReplayIter, Select, Series, _lift2

# ------------------------------------------------------------------ selects


def exact[K, V]() -> Select[K, V, K]:
    """Select the single cell whose key equals the query; nothing when absent.

    Uses the stream's hash index, so repeated exact queries cost O(1) once
    the stream has been pulled through the key. A missing key selects the
    empty tuple — pair with :func:`only` to raise or :func:`only_or` to
    default.
    """

    def sel(replay: ReplayIter[K, V], q: K) -> tuple[tuple[K, F[V]], ...]:
        try:
            return ((q, replay.find(q)),)
        except KeyError:
            return ()

    return sel


def clip_daily(fill: float | None = None) -> Select[Period, float, Period]:
    """Select cells overlapping the query window, prorated by day count.

    Cells fully inside the window pass through untouched (original nodes).
    Partial overlaps yield the clipped period and the cell scaled by
    ``overlap_days / period_days`` — values accrue uniformly across their
    period. With ``fill``, window time not covered by any period yields
    explicit ``(gap_period, Pure(fill))`` pairs; otherwise gaps are omitted.
    Scanning starts at the first period overlapping the window and stops at
    the first period starting at or past its end, so infinite series
    terminate.
    """

    def sel(replay: ReplayIter[Period, float], q: Period) -> tuple[tuple[Period, F[float]], ...]:
        out: list[tuple[Period, F[float]]] = []
        cursor = q.start
        for period, cell in replay.iter_from(q):
            if period.start >= q.end:
                break
            lo = max(period.start, q.start)
            hi = min(period.end, q.end)
            if hi <= lo:
                continue
            if fill is not None and lo > cursor:
                out.append((Period(cursor, lo), Pure(fill)))
            days = (period.end - period.start).days
            part = (hi - lo).days
            if part == days:
                out.append((period, cell))
            else:
                clipped = Period(lo, hi)
                out.append(
                    (
                        clipped,
                        cell.map(
                            lambda v, s=part / days: v * s,
                            label=f"{period} clipped to {clipped}",
                        ),
                    )
                )
            cursor = hi
        if fill is not None and cursor < q.end:
            out.append((Period(cursor, q.end), Pure(fill)))
        return tuple(out)

    return sel


# ------------------------------------------------------------------ reduces


def only[K, V]() -> Reduce[K, V]:
    """Exactly one selected cell answers the query: return it untouched.

    Raises ``KeyError`` when nothing was selected and ``ValueError`` when the
    selection is ambiguous.
    """

    def red(pairs: tuple[tuple[K, F[V]], ...]) -> F[V]:
        if len(pairs) == 1:
            return pairs[0][1]
        if not pairs:
            raise KeyError("no cell selected")
        raise ValueError(f"expected exactly one selected cell, got {len(pairs)}")

    return red


def only_or[K, V](default: V) -> Reduce[K, V]:
    """Like :func:`only`, but an empty selection evaluates to ``default``."""

    def red(pairs: tuple[tuple[K, F[V]], ...]) -> F[V]:
        if len(pairs) == 1:
            return pairs[0][1]
        if not pairs:
            return Pure(default)
        raise ValueError(f"expected at most one selected cell, got {len(pairs)}")

    return red


def total[K](empty: float = 0.0) -> Reduce[K, float]:
    """Sum the selected cells; ``empty`` when nothing is selected.

    A fold of one returns the cell untouched.
    """

    def red(pairs: tuple[tuple[K, F[float]], ...]) -> F[float]:
        if not pairs:
            return Pure(empty)
        acc = pairs[0][1]
        for _, cell in pairs[1:]:
            acc = _lift2(lambda a, b: a + b, acc, cell)
        return acc

    return red


# ------------------------------------------------------------------ presets


def flow(
    cells: Callable[[], Iterable[tuple[Period, F[float]]]], *, label: str
) -> Series[Period, float, Period]:
    """A ``Period``-keyed flow line item.

    Queries are windows: overlapping cells are prorated by day count and
    summed; a window touching no periods evaluates to ``0.0``.
    """
    return Series.from_cells(cells, clip_daily(), total(0.0), label=label)


def keyed[K, V](cells: Callable[[], Iterable[tuple[K, F[V]]]], *, label: str) -> Series[K, V, K]:
    """An exact-keyed line item: the query is the key; missing keys raise."""
    return Series.from_cells(cells, exact(), only(), label=label)
