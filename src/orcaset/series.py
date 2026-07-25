# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Line-item series over the free monad core.

A :class:`Series` is a financial line item: an ordered stream of
``(key, F[value])`` cells plus a query convention — two functions fixed at
construction:

- ``select`` narrows the materialized stream to the ``(key, cell)`` pairs
  that answer a query, clipping or otherwise transforming pairs as needed.
  Its output is the complete, self-describing evidence for a query's value.
- ``reduce`` collapses the selected pairs to a single value.

Identity is what makes caching correct:

- Each series holds exactly one stream node, built at construction. Construct
  a series once per model and share it by reference; never rebuild the same
  logical series.
- :meth:`Series.select` and :meth:`Series.query` return one memoized node per
  ``(series, query)``, keyed by query equality, so every reference to the
  same question shares a single graph node and repeated calls are O(1).
- Values are cached per :class:`~orcaset.context.Context`. Evaluating in a
  fresh context re-runs the cell factory from scratch.

Key discipline (assumed by the machinery, enforced by convention): keys are
hashable and totally ordered, each series yields its keys in strictly
increasing order, and queries are hashable and immutable. Select and reduce
functions must be deterministic, must never evaluate nodes (no ``run``), and
should return original cell nodes on trivial paths (an unclipped pair, a
fold of one) so shared cells stay shared graph nodes.

Recursive definitions query the series being defined: a cell references
``series.query(prior_window)`` for whatever it depends on, so dependencies
are stated in key terms rather than stream positions and survive re-keying
(e.g. monthly to quarterly). Standard conventions live in
:mod:`orcaset.conventions`.
"""

from __future__ import annotations

import heapq
from bisect import bisect_left
from collections.abc import Callable, Iterable, Iterator, Sequence
from itertools import groupby
from typing import Any, cast

from .context import Context
from .f import Delay, F, Pure


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

        Hash-indexed: repeated lookups are O(1) once the stream has been
        pulled through ``key``. Raises ``KeyError`` if the stream passes or
        exhausts without yielding ``key``.
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

    def iter_from(self, key: K) -> Iterator[tuple[K, F[V]]]:
        """Iterate pairs from the first key not strictly less than ``key``.

        Relies on keys arriving in increasing order: pulls the stream until it
        reaches or passes ``key``, then bisects the buffer, so window selects
        skip the prefix instead of rescanning it on every query.
        """
        while not self._items or self._items[-1][0] < key:  # type: ignore[operator]
            if not self._pull():
                break
        i = bisect_left(self._items, key, key=lambda item: item[0])  # type: ignore[bad-argument-type]
        while True:
            if i >= len(self._items) and not self._pull():
                return
            yield self._items[i]
            i += 1

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


type Select[K, V, Q] = Callable[[ReplayIter[K, V], Q], tuple[tuple[K, F[V]], ...]]
"""Narrow a stream to the (possibly clipped) ``(key, cell)`` pairs answering ``Q``.

Pure and deterministic: may transform keys and construct new cell nodes as
data (e.g. scale a partial period) but must never evaluate them, and must
return original cell nodes when no transformation applies. Coverage and gap
policy live here — the output is the full evidence handed to ``Reduce``.
"""

type Reduce[K, V] = Callable[[tuple[tuple[K, F[V]], ...]], F[V]]
"""Collapse selected ``(key, cell)`` pairs to a single value node.

Pure and deterministic: sees exactly the select output and should return the
lone cell untouched when reducing a single pair.
"""


class Series[K, V, Q = K]:
    """A financial line item: an ordered stream of ``(key, F[value])`` cells
    plus the select/reduce convention that answers queries against it.

    ``stream`` is the single graph node whose per-context value is the
    :class:`ReplayIter` materialization of this series.
    """

    __slots__ = ("_queries", "_reduce", "_select", "_selects", "_stream", "label")

    def __init__(
        self,
        stream: F[ReplayIter[K, V]],
        select: Select[K, V, Q],
        reduce: Reduce[K, V],
        *,
        label: str,
    ) -> None:
        self.label = label
        self._stream: F[ReplayIter[K, V]] = stream
        self._select = select
        self._reduce = reduce
        self._selects: dict[Q, F[tuple[tuple[K, F[V]], ...]]] = {}
        self._queries: dict[Q, F[V]] = {}

    def __repr__(self) -> str:
        return f"Series({self.label!r})"

    @classmethod
    def from_cells(
        cls,
        cells: Callable[[], Iterable[tuple[K, F[V]]]],
        select: Select[K, V, Q],
        reduce: Reduce[K, V],
        *,
        label: str,
    ) -> Series[K, V, Q]:
        """Define a series from a factory of ``(key, cell)`` pairs.

        The factory runs once per context. It may reference the series being
        defined through ``query`` (nodes are inert until evaluated); it must
        be deterministic and must not evaluate its own cells.
        """
        return cast(
            Series[K, V, Q],
            Series(
                Delay(lambda: ReplayIter(cells()), label=f"{label} stream"),
                select,
                reduce,
                label=label,
            ),
        )

    @classmethod
    def from_pairs(
        cls,
        pairs: Iterable[tuple[K, V]],
        select: Select[K, V, Q],
        reduce: Reduce[K, V],
        *,
        label: str,
    ) -> Series[K, V, Q]:
        """Define an input series from plain ``(key, value)`` pairs.

        Values are lifted with ``Pure`` once at construction, so input cells
        are model-owned nodes shared across contexts.
        """
        items: list[tuple[K, F[V]]] = [(key, Pure(value)) for key, value in pairs]
        return cls.from_cells(lambda: items, select, reduce, label=label)

    def select(self, q: Q) -> F[tuple[tuple[K, F[V]], ...]]:
        """The selection ``Label.select[q]``: one shared node per (series, query).

        Evaluates to the (possibly clipped) ``(key, cell)`` pairs that answer
        ``q`` — the audit view behind :meth:`query`. Cells stay lazy; run them
        in the same context to see the values they contribute.
        """
        node = self._selects.get(q)
        if node is None:
            sel = self._select
            node = self._stream.map(
                lambda replay: sel(replay, q), label=f"{self.label}.select[{q}]"
            )
            self._selects[q] = node
        return node

    def query(self, q: Q) -> F[V]:
        """The value of this series at ``q``: one shared node per (series, query).

        ``query`` is the sole retrieval interface: ``reduce(select(q))``.
        Evaluation forces only the cells the convention selects.
        """
        node = self._queries.get(q)
        if node is None:
            red = self._reduce
            label = f"{self.label}[{q}]"

            def reduce_pairs(pairs: tuple[tuple[K, F[V]], ...]) -> F[V]:
                try:
                    return red(pairs)
                except Exception as err:
                    err.add_note(f"while reducing {label}")
                    raise

            node = self.select(q).bind(reduce_pairs, label=label)
            self._queries[q] = node
        return node

    def items(self, ctx: Context) -> Iterator[tuple[K, F[V]]]:
        """Iterate ``(key, cell)`` pairs by materializing the stream in ``ctx``."""
        return iter(self._stream.run(ctx))

    def map[W](
        self,
        f: Callable[[V], W],
        *,
        select: Select[K, W, Q] | None = None,
        reduce: Reduce[K, W] | None = None,
        label: str,
    ) -> Series[K, W, Q]:
        """Pointwise transform. Derived cells reference this series' cells.

        The select/reduce convention is inherited unless overridden. An
        inherited convention must make sense for ``W``: the derived series is
        its own line item, so queries clip and fold the mapped values.
        """

        def wrap(replay: ReplayIter[K, V]) -> ReplayIter[K, W]:
            def cells() -> Iterator[tuple[K, F[W]]]:
                for key, cell in replay:
                    yield key, cell.map(f, label=f"{label}@{key}")

            return ReplayIter(cells())

        return cast(
            Series[K, W, Q],
            Series(
                self._stream.map(wrap, label=f"{label} stream"),
                select if select is not None else cast("Select[K, W, Q]", self._select),
                reduce if reduce is not None else cast("Reduce[K, W]", self._reduce),
                label=label,
            ),
        )

    @staticmethod
    def map2[K2, A, B, W, Q2](
        a: Series[K2, A, Q2],
        b: Series[K2, B, Any],
        f: Callable[[A, B], W],
        *,
        select: Select[K2, W, Q2] | None = None,
        reduce: Reduce[K2, W] | None = None,
        label: str,
    ) -> Series[K2, W, Q2]:
        """Combine two key-aligned series pointwise.

        Streams are zipped strictly: iteration stops at the shorter series and
        raises ``ValueError`` if keys ever disagree. The select/reduce
        convention comes from ``a`` unless overridden.
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
        return Series(
            stream,
            select if select is not None else cast("Select[K2, W, Q2]", a._select),
            reduce if reduce is not None else cast("Reduce[K2, W]", a._reduce),
            label=label,
        )

    @staticmethod
    def merge[K2, V2, Q2](
        items: Sequence[Series[K2, V2, Q2]],
        combine: Callable[[V2, V2], V2],
        *,
        select: Select[K2, V2, Q2] | None = None,
        reduce: Reduce[K2, V2] | None = None,
        label: str,
    ) -> Series[K2, V2, Q2]:
        """Ordered outer-merge of several series, combining cells on equal keys.

        Keys absent from a series are passed through from the others, so the
        result covers the union of keys in key order. The select/reduce
        convention comes from the first series unless overridden.
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
                    group_cells = (cell for _, cell in group)
                    acc = next(group_cells)
                    for cell in group_cells:
                        acc = _lift2(combine, acc, cell, label=f"{label}@{key}")
                    yield key, acc

            return ReplayIter(cells())

        gathered: F[tuple[ReplayIter[K2, V2], ...]] = Pure(())
        for series in items:
            gathered = gathered.bind(
                lambda replays, series=series: series._stream.map(lambda replay: (*replays, replay))
            )
        return Series(
            gathered.map(wrap, label=f"{label} stream"),
            select if select is not None else items[0]._select,
            reduce if reduce is not None else items[0]._reduce,
            label=label,
        )
