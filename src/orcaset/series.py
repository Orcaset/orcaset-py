# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Line-item series over the free monad core.

A :class:`Series` is a financial line item: an ordered stream of
``(key, F[value])`` cells. It owns the identity that makes caching correct:

- Each series holds exactly one stream node, built at construction. Construct
  a series once per model and share it by reference; never rebuild the same
  logical series.
- :meth:`Series.at` returns one memoized cell-address node per key
  (``"Label@key"``), so every reference to the same cell shares a single
  graph node.
- Values are cached per :class:`~orcaset.context.Context`. Evaluating in a
  fresh context re-runs the cell factory from scratch.

Key discipline (assumed by the machinery, enforced by convention): keys are
hashable and totally ordered, and each series yields its keys in strictly
increasing order, so lookups can stop as soon as the stream passes the
requested key.

Recursive definitions are written as unfolds: carry the previous cell in
generator state so each cell references its predecessor directly. Use
``at``/``get`` for references *between* series.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import date
from functools import reduce
from itertools import groupby

from .context import Context
from .f import Delay, F, Pure
from .period import Period


def _lift2[A, B, W](
    f: Callable[[A, B], W], fa: F[A], fb: F[B], *, label: str | None = None
) -> F[W]:
    """Combine two cells pointwise. Parameters keep closures loop-safe."""
    return fa.bind(lambda a: fb.map(lambda b: f(a, b)), label=label)


class ReplayIter[K, V]:
    """Buffered replay of one materialization of a series stream.

    Cells are pulled from the underlying iterator on demand, buffered, and
    indexed by key. A ``ReplayIter`` is per-context state: it lives in a
    context cache as the value of a series' stream node, so the underlying
    iterator is advanced at most once per position per context.
    """

    __slots__ = ("_exhausted", "_index", "_items", "_iter")

    def __init__(self, source: Iterable[tuple[K, F[V]]]) -> None:
        self._items: list[tuple[K, F[V]]] = []
        self._index: dict[K, F[V]] = {}
        self._iter: Iterator[tuple[K, F[V]]] = iter(source)
        self._exhausted: bool = False

    def __iter__(self) -> Iterator[tuple[K, F[V]]]:
        i = 0
        while True:
            if i >= len(self._items) and not self._pull():
                return
            yield self._items[i]
            i += 1

    def find(self, key: K) -> F[V]:
        """Return the cell at ``key``, pulling the stream forward as needed.

        Raises ``KeyError`` if the stream passes or exhausts without yielding
        ``key``.
        """
        cell = self._index.get(key)
        if cell is not None:
            return cell
        while self._pull():
            kk, _ = self._items[-1]
            if kk == key:
                return self._index[key]
            if kk > key:  # type: ignore[operator]
                break
        raise KeyError(key)

    def _pull(self) -> bool:
        if self._exhausted:
            return False
        try:
            kk, fv = next(self._iter)
        except StopIteration:
            self._exhausted = True
            return False
        self._items.append((kk, fv))
        if kk not in self._index:
            self._index[kk] = fv
        return True


class Series[K, V]:
    """A financial line item: an ordered stream of ``(key, F[value])`` cells.

    ``stream`` is the single graph node whose per-context value is the
    :class:`ReplayIter` materialization of this series.
    """

    __slots__ = ("_cells", "_stream", "label")

    def __init__(self, stream: F[ReplayIter[K, V]], *, label: str) -> None:
        self.label = label
        self._stream: F[ReplayIter[K, V]] = stream
        self._cells: dict[K, F[V]] = {}

    def __repr__(self) -> str:
        return f"Series({self.label!r})"

    @classmethod
    def from_cells(
        cls, cells: Callable[[], Iterable[tuple[K, F[V]]]], *, label: str
    ) -> Series[K, V]:
        """Define a series from a factory of ``(key, cell)`` pairs.

        The factory runs once per context. Generator locals are the idiomatic
        place to thread recursive state (the prior cell); the factory must be
        deterministic.
        """
        return cls(
            Delay(lambda: ReplayIter(cells()), label=f"{label} stream"),
            label=label,
        )

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[K, V]], *, label: str) -> Series[K, V]:
        """Define an input series from plain ``(key, value)`` pairs.

        Values are lifted with ``Pure`` once at construction, so input cells
        are model-owned nodes shared across contexts.
        """
        items: list[tuple[K, F[V]]] = [(key, Pure(value)) for key, value in pairs]
        return cls.from_cells(lambda: items, label=label)

    def at(self, key: K) -> F[V]:
        """The cell address ``Label@key``: one shared node per (series, key).

        Evaluation forces the stream through ``key``; a key the series never
        yields raises ``KeyError``.
        """
        cell = self._cells.get(key)
        if cell is None:
            cell = self._stream.bind(lambda replay: replay.find(key), label=f"{self.label}@{key}")
            self._cells[key] = cell
        return cell

    def get(self, key: K, default: V) -> F[V]:
        """Like :meth:`at`, but evaluates to ``default`` when ``key`` is absent."""

        def lookup(replay: ReplayIter[K, V]) -> F[V]:
            try:
                return replay.find(key)
            except KeyError:
                return Pure(default)

        return self._stream.bind(lookup, label=f"{self.label}@{key}?")

    def items(self, ctx: Context) -> Iterator[tuple[K, F[V]]]:
        """Iterate ``(key, cell)`` pairs by materializing the stream in ``ctx``."""
        return iter(self._stream.run(ctx))

    def between(
        self: Series[Period, float], start: date, end: date, *, label: str | None = None
    ) -> F[float]:
        """Aggregate a period-keyed flow series over ``[start, end)``.

        Sums every cell whose period overlaps the window, prorating partial
        overlaps by day count (values accrue uniformly across their period).
        Time not covered by any period contributes zero, so a window touching
        no periods evaluates to ``0.0``. Zero-length periods are skipped.
        """

        def aggregate(replay: ReplayIter[Period, float]) -> F[float]:
            total: F[float] | None = None
            for period, cell in replay:
                if period.start >= end:
                    break
                overlap = (min(period.end, end) - max(period.start, start)).days
                if overlap <= 0:
                    continue
                span = (period.end - period.start).days
                if span == 0:
                    continue
                part = cell if overlap == span else cell.map(lambda v, f=overlap / span: v * f)
                total = part if total is None else _lift2(lambda a, b: a + b, total, part)
            return total if total is not None else Pure(0.0)

        return self._stream.bind(aggregate, label=label or f"{self.label}[{start}..{end}]")

    def map[W](self, f: Callable[[V], W], *, label: str) -> Series[K, W]:
        """Pointwise transform. Derived cells reference this series' cells."""

        def wrap(replay: ReplayIter[K, V]) -> ReplayIter[K, W]:
            def cells() -> Iterator[tuple[K, F[W]]]:
                for key, cell in replay:
                    yield key, cell.map(f, label=f"{label}@{key}")

            return ReplayIter(cells())

        return Series(self._stream.map(wrap, label=f"{label} stream"), label=label)

    @staticmethod
    def map2[K2, A, B, W](
        a: Series[K2, A],
        b: Series[K2, B],
        f: Callable[[A, B], W],
        *,
        label: str,
    ) -> Series[K2, W]:
        """Combine two key-aligned series pointwise.

        Streams are zipped strictly: iteration stops at the shorter series and
        raises ``ValueError`` if keys ever disagree.
        """

        def wrap(ra: ReplayIter[K2, A], rb: ReplayIter[K2, B]) -> ReplayIter[K2, W]:
            def cells() -> Iterator[tuple[K2, F[W]]]:
                for (ka, ca), (kb, cb) in zip(ra, rb):
                    if ka != kb:
                        raise ValueError(f"misaligned keys: {ka!r} != {kb!r}")
                    yield ka, _lift2(f, ca, cb, label=f"{label}@{ka}")

            return ReplayIter(cells())

        stream = a._stream.bind(
            lambda ra: b._stream.map(lambda rb: wrap(ra, rb)),
            label=f"{label} stream",
        )
        return Series(stream, label=label)

    @staticmethod
    def merge[K2, V2](
        items: Sequence[Series[K2, V2]],
        combine: Callable[[V2, V2], V2],
        *,
        label: str,
    ) -> Series[K2, V2]:
        """Ordered outer-merge of several series, combining cells on equal keys.

        Keys absent from a series are passed through from the others, so the
        result covers the union of keys in key order.
        """
        if not items:
            raise ValueError("merge requires at least one series")

        def wrap(replays: tuple[ReplayIter[K2, V2], ...]) -> ReplayIter[K2, V2]:
            def cells() -> Iterator[tuple[K2, F[V2]]]:
                merged = heapq.merge(
                    *replays,
                    key=lambda item: item[0],  # type: ignore[bad-argument-type]
                )
                for key, group in groupby(merged, key=lambda item: item[0]):
                    group_cells = [cell for _, cell in group]
                    yield (
                        key,
                        reduce(
                            lambda ca, cb: _lift2(combine, ca, cb, label=f"{label}@{key}"),
                            group_cells,
                        ),
                    )

            return ReplayIter(cells())

        gathered: F[tuple[ReplayIter[K2, V2], ...]] = Pure(())
        for series in items:
            gathered = gathered.bind(
                lambda replays, series=series: series._stream.map(lambda replay: (*replays, replay))
            )
        return Series(gathered.map(wrap, label=f"{label} stream"), label=label)
