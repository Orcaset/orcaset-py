# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Select and reduce conventions for :class:`~orcaset.series.LeafSeries`.

A convention pair defines how a leaf answers queries: ``select`` narrows the
ordered cell stream to the (possibly clipped) cells relevant to a query, and
``reduce`` collapses those cells to one answer. Both are pure: they may
construct nodes as data but never evaluate them, and they preserve node
identity on trivial paths so shared cells stay shared graph nodes.

``select`` never raises for want of coverage — it returns ``()`` — and
``reduce`` is total, so the empty selection is where a convention states what
"nothing here" means. Two answers are principled:

- :data:`~orcaset.maybe.MISSING`, for point-valued lines where a key either
  has data or does not (:func:`only`).
- a declared neutral value, for lines where emptiness has a meaning: no
  activity in a window is zero flow (:func:`sum_cells` with ``empty=0.0``).

Compose a leaf with ``LeafSeries.from_cells`` (or ``from_pairs``): a common
flow line is ``clip_daily()`` with ``sum_cells(0.0)``; an exact-keyed line is
``exact()`` with ``only()``.
"""

from __future__ import annotations

from .f import F, Pure
from .maybe import MISSING, MISSING_NODE, Maybe, Missing
from .period import Period
from .series import Cell, CellReplay, Key, Reduce, Select, lift2

# Selects ------------------------------------------------------------------


def exact[K: Key, V]() -> Select[K, V, K]:
    """Select the single cell whose key equals the query; nothing when absent.

    Uses the stream's hash index, so repeated exact queries cost O(1) once
    the stream has been pulled through the key. A missing key selects the
    empty tuple — pair with :func:`only` to answer ``MISSING`` or
    :func:`only_or` to default.
    """

    def sel(replay: CellReplay[K, V], q: K) -> tuple[Cell[K, V], ...]:
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

    def sel(replay: CellReplay[Period, float], q: Period) -> tuple[Cell[Period, float], ...]:
        out: list[Cell[Period, float]] = []
        cursor = q.start
        # Walk by endpoint dates rather than Period ordering: a query window
        # often overlaps cells, and overlapping Periods are incomparable.
        for period, cell in replay:
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


# Reduces ------------------------------------------------------------------


def only[K, V]() -> Reduce[K, V]:
    """At most one selected cell answers the query.

    Returns the cell untouched when exactly one was selected,
    :data:`~orcaset.maybe.MISSING` when none was, and raises ``ValueError``
    when the selection is ambiguous.
    """

    def red(pairs: tuple[Cell[K, V], ...]) -> F[Maybe[V]]:
        if len(pairs) == 1:
            return pairs[0][1]
        if not pairs:
            return MISSING_NODE
        raise ValueError(f"expected at most one selected cell, got {len(pairs)}")

    return red


def only_or[K, V](default: V) -> Reduce[K, V]:
    """Like :func:`only`, but an empty selection answers ``default``.

    Use where a line item genuinely has a neutral value outside its cells;
    otherwise leave the answer ``MISSING`` and fill at the point of use, so
    the gap stays visible.
    """

    def red(pairs: tuple[Cell[K, V], ...]) -> F[Maybe[V]]:
        if len(pairs) == 1:
            return pairs[0][1]
        if not pairs:
            return Pure(default)
        raise ValueError(f"expected at most one selected cell, got {len(pairs)}")

    return red


def sum_cells[K](empty: Maybe[float] = MISSING) -> Reduce[K, float]:
    """Sum the selected cells; answer ``empty`` when nothing was selected.

    A fold of one returns the cell untouched. The default leaves an
    uncovered query ``MISSING``; pass ``0.0`` for flow-like lines where no
    coverage means no activity.
    """

    def red(pairs: tuple[Cell[K, float], ...]) -> F[Maybe[float]]:
        if not pairs:
            return MISSING_NODE if isinstance(empty, Missing) else Pure(empty)
        acc = pairs[0][1]
        for _, cell in pairs[1:]:
            acc = lift2(lambda a, b: a + b, acc, cell)
        return acc

    return red
