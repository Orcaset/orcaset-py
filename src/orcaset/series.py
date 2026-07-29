# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from abc import ABC
from collections.abc import Callable, Generator, Hashable, Iterable, Iterator, Sequence
from typing import Any, Protocol, Self

from orcaset.maybe import Maybe, Na
from orcaset.maybe import isna as _isna
from orcaset.rule import Rule, Step, fetch

isna = _isna
"""Compatibility re-export; import new code from ``orcaset.maybe``."""

# ---------- keys ----------


class Key(Hashable, Protocol):
    """Series key: hashable (cell identity) and comparable (lazy scans).

    ``a < b`` means "a is entirely before b". The order need not be total:
    keys that overlap (e.g. overlapping ``Period``s) may be mutually
    incomparable. Scans only require that domain streams are strictly
    ascending, so anything entirely past a probe stays past it.
    """

    def __lt__(self, other: Self, /) -> bool: ...


type Keys[K: Key] = Iterable[K]
"""Contract: strictly ascending (each key entirely before the next, hence
disjoint); possibly infinite; replayable (safe to re-iterate)."""

type MergeKeysFn[K: Key] = Callable[[tuple[Keys[K], ...]], Iterable[K]]
"""Lazily merge a finite tuple of source domains into one ascending domain."""


# ---------- replayable keys ----------


class _ReplayableIterator[T](Iterator[T]):
    def __init__(self, owner: Replayable[T]) -> None:
        self._owner = owner
        self._index = 0

    def __next__(self) -> T:
        if self._index < len(self._owner._buffer):
            item = self._owner._buffer[self._index]
        else:
            item = next(self._owner._source)
            self._owner._buffer.append(item)
        self._index += 1
        return item


class Replayable[T](Iterable[T]):
    """Buffered iterable that can be re-iterated without re-consuming the source.

    Items are pulled lazily from the source and appended to a shared buffer, so
    the source may be infinite. Each call to ``iter`` returns a new iterator
    that replays from the start of the buffer.
    """

    def __init__(self, iterable: Iterable[T]) -> None:
        self._source = iter(iterable)
        self._buffer: list[T] = []

    def __iter__(self) -> Iterator[T]:
        return _ReplayableIterator(self)


# ---------- series ----------


class Series[Q: Hashable, K: Key, W](Rule[Q, W], ABC):
    """The series interface: a demandable rule with an explicit time domain.

    Public surface: ``demand(self, q)`` and ``self.keys``. How answers are
    produced is up to the implementation (grid + query semantics, delegation,
    ...); downstream code should type against this.
    """

    def __init__(self, name: str, keys: Rule[None, Keys[K]] | Callable[[], Iterable[K]]):
        super().__init__(name)
        self.keys: Rule[None, Keys[K]] = keys if isinstance(keys, Rule) else _KeysCell(name, keys)

    def map[W2](self, name: str, fn: Callable[[W], W2]) -> MapSeries[Q, K, W, W2]:
        """Derived series answering ``fn(self answered at q)`` for every query.

        ``fn`` sees the raw answer (typically ``Maybe``) and owns the miss policy.
        """
        return MapSeries(name, self, fn)


type SeriesSources[Q: Hashable, K: Key, W] = tuple[
    Series[Q, K, W],
    *tuple[Series[Q, K, W], ...],
]
"""A nonempty, homogeneous tuple of series."""

type MapNFn[W, W2] = Callable[[tuple[W, ...]], W2]
"""Combine the answers from a nonempty tuple of source series."""


class CellReader[K: Key, V](Protocol):
    """Narrow view of a grid series handed to value functions."""

    def cell(self, key: K, /) -> Step[Maybe[V]]: ...


type ValueFn[K: Key, V] = Callable[[CellReader[K, V], K], Step[V] | V]
"""Grid definition; may assume key is covered.

Recurrences: ``yield from reader.cell(prior_k)``. Other rules/series: fetch
their public face. May return a plain value or a generator ``Step``.
"""

type SelectFn[Q, K: Key] = Callable[[Keys[K], Q], Sequence[K]]
"""Pure. Grid keys relevant to ``q`` (overlap, bracketing, ...).

Early-terminating scan of an ascending, possibly infinite stream. May return
keys outside the domain (their cells resolve to ``Na``); whichever convention
a select picks, its paired ``reduce`` must expect it.
"""

type ReduceFn[Q, K: Key, V, W] = Callable[[Q, Sequence[tuple[K, Maybe[V]]]], W]
"""Pure. Combine fetched cells into the answer.

Owns the policy for misses and partial coverage (``q`` not spanned by the
selected keys).
"""


class GridSeries[Q: Hashable, K: Key, V, W](Series[Q, K, W]):
    """A series backed by a grid of memoized cells, with packaged query semantics.

    All three ingredients are constructor state: ``value_at`` is the instance
    data (the grid definition); ``select``/``reduce`` are the query semantics,
    fixed per series at construction so a series can never be read under a
    convention other than its own. ``select`` and ``reduce`` are a matched
    pair — construction helpers are the natural place to pair them.
    """

    def __init__(
        self,
        name: str,
        keys: Rule[None, Keys[K]] | Callable[[], Iterable[K]],
        value_at: ValueFn[K, V],
        *,
        select: SelectFn[Q, K],
        reduce: ReduceFn[Q, K, V, W],
    ):
        super().__init__(name, keys)
        self._value_at = value_at
        self._select = select
        self._reduce = reduce
        self._cells: Rule[K, Maybe[V]] = _Cells(name, self)

    # ---- grid reads ----

    def cell(self, key: K, /) -> Step[Maybe[V]]:
        """Blessed grid read: memoized, total (off-domain -> ``Na``), traced.

        No query semantics apply; this is an exact-key lookup.
        """
        return fetch(self._cells, key)

    # ---- query template ----

    def compute(self, q: Q, /) -> Step[W]:
        ks = yield from fetch(self.keys, None)
        items: list[tuple[K, Maybe[V]]] = []
        for k in self._select(ks, q):
            v = yield from fetch(self._cells, k)
            items.append((k, v))
        return self._reduce(q, items)


class MapSeries[Q: Hashable, K: Key, W, W2](Series[Q, K, W2]):
    """A series whose every answer is ``fn(source answered at q)``.

    Query resolution is fully delegated to the source; there is no grid of its
    own. ``keys`` aliases the source's domain so downstream series can share it
    and traces show the dependency. ``fn`` sees the source's raw answer
    (typically ``Maybe``) and owns the miss policy.
    """

    def __init__(self, name: str, source: Series[Q, K, W], fn: Callable[[W], W2]):
        super().__init__(name, source.keys)
        self._source = source
        self._fn = fn

    def compute(self, q: Q, /) -> Step[W2]:
        w = yield from fetch(self._source, q)
        return self._fn(w)


class MapNSeries[Q: Hashable, K: Key, W, W2](Series[Q, K, W2]):
    """A series whose every answer combines source answers at the same query.

    Query resolution is delegated independently to every source. ``merge_keys``
    only constructs the derived series' public domain; it is not involved when
    answering a query.
    """

    def __init__(
        self,
        name: str,
        sources: SeriesSources[Q, K, W],
        fn: MapNFn[W, W2],
        *,
        merge_keys: MergeKeysFn[K],
    ) -> None:
        if not sources:
            raise ValueError("MapNSeries requires at least one source")
        super().__init__(name, _MapNKeys(name, sources, merge_keys))
        self._sources = sources
        self._fn = fn

    def compute(self, q: Q, /) -> Step[W2]:
        values: list[W] = []
        for source in self._sources:
            values.append((yield from fetch(source, q)))
        return self._fn(tuple(values))


# ---------- internal glue ----------


class _KeysCell[K: Key](Rule[None, Keys[K]]):
    """Demandable domain: one Replayable buffer per context, shared by every
    consumer (face, cells, external readers, aliasing series).

    Validates the ascending-keys contract lazily as keys are first pulled.
    """

    def __init__(self, name: str, key_iter: Callable[[], Iterable[K]]):
        super().__init__(f"{name}.keys")
        self._key_iter = key_iter

    def compute(self, key: None) -> Keys[K]:
        return Replayable(_ascending(self._key_iter()))


class _MapNKeys[Q: Hashable, K: Key, W](Rule[None, Keys[K]]):
    """Demandable, replayable domain derived from several source domains."""

    def __init__(
        self,
        name: str,
        sources: SeriesSources[Q, K, W],
        merge: MergeKeysFn[K],
    ) -> None:
        super().__init__(f"{name}.keys")
        self._sources = sources
        self._merge = merge

    def compute(self, key: None, /) -> Step[Keys[K]]:
        domains: list[Keys[K]] = []
        for source in self._sources:
            domains.append((yield from fetch(source.keys, None)))
        return Replayable(_ascending(self._merge(tuple(domains))))


class _Cells[K: Key, V](Rule[K, Maybe[V]]):
    """Internal grid; total (uncovered -> Na).

    Reachable only via the owning series object — privacy is structural, not
    conventional.
    """

    def __init__(self, name: str, series: GridSeries[Any, K, V, Any]):
        super().__init__(f"{name}.cells")
        self._series = series

    def compute(self, key: K) -> Step[Maybe[V]]:
        ks = yield from fetch(self._series.keys, None)
        if not _covered(ks, key):
            return Na
        return (yield from _as_step(self._series._value_at(self._series, key)))


def _ascending[K: Key](source: Iterable[K]) -> Iterator[K]:
    """Yield from `source`, raising if consecutive keys are not strictly ascending."""
    prev: K | None = None
    for k in source:
        if prev is not None and not prev < k:
            raise ValueError(f"keys must be strictly ascending: got {prev!r} then {k!r}")
        prev = k
        yield k


def _covered[K: Key](keys: Keys[K], key: K) -> bool:
    """Ascending scan: found -> True; passed or exhausted -> False."""
    for k in keys:
        if k == key:
            return True
        if key < k:
            return False
    return False


def _as_step[V](value: Step[V] | V) -> Step[V]:
    """Normalize plain-vs-generator, same dual ``Rule.compute`` already has."""
    if isinstance(value, Generator):
        return value

    def completed() -> Step[V]:
        if False:
            yield
        return value

    return completed()
