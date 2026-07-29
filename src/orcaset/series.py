# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Hashable, Iterable, Iterator
from typing import Any, Protocol, Self

from orcaset.rule import Rule, Step, fetch

# ---------- keys ----------


class Key(Hashable, Protocol):
    """Series key: hashable (cell identity) and comparable (lazy scans).

    ``a < b`` means "a is entirely before b". The order need not be total:
    keys that overlap (e.g. overlapping ``Period``s) may be mutually
    incomparable. Scans only require that domain streams are strictly
    ascending, so anything entirely past a probe stays past it.
    """

    def __lt__(self, other: Self, /) -> bool: ...


type QueryFn[Q, K: Key, V, W] = Callable[
    [Q, Iterable[tuple[K, Step[V] | V]]],
    Step[W] | W,
]
"""Fold a query over a lazy cell stream into an answer.

May scan without forcing every ``Step`` (early-terminate, skip). Fixed per
series at construction so a series cannot be read under another convention.
"""

type SeriesSources[Q: Hashable, K: Key, W] = tuple[
    Series[Q, K, W],
    *tuple[Series[Q, K, W], ...],
]
"""A nonempty, homogeneous tuple of series."""


# ---------- replayable ----------


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
    """A demandable rule with an explicit time domain.

    Public surface: ``compute`` (via ``Rule``) and ``keys()``. Values are only
    reachable through ``compute``, so every answer is dependency-tracked.
    """

    @abstractmethod
    def keys(self) -> Rule[None, Iterable[K]]:
        """Demandable ascending domain (strictly ascending, possibly infinite)."""
        ...

    def map[V](self, name: str, fn: Callable[[W], V]) -> MapSeries[Q, K, W, V]:
        """Derived series answering ``fn(self answered at q)`` for every query.

        ``fn`` sees the raw answer (typically ``Maybe``) and owns the miss policy.
        Domain aliases ``self.keys()``.
        """
        return MapSeries(name, self, fn)

    def map2[W2, V](
        self,
        name: str,
        other: Series[Q, K, W2],
        fn: Callable[[W, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[K], ...]], Iterable[K]],
    ) -> Map2Series[Q, K, W, W2, V]:
        """Combine ``self`` and ``other`` at each query via ``fn``.

        Sources may have different answer types. ``merge_keys`` builds the
        derived domain only.
        """
        return Map2Series(name, self, other, fn, merge_keys=merge_keys)


class MapSeries[Q: Hashable, K: Key, W, V](Series[Q, K, V]):
    """A series whose every answer is ``fn(source answered at q)``.

    Query resolution is fully delegated to the source; ``keys()`` returns the
    source domain rule so both share one buffer per context and traces show the
    dependency.
    """

    def __init__(self, name: str, source: Series[Q, K, W], fn: Callable[[W], V]) -> None:
        super().__init__(name)
        self._source = source
        self._fn = fn

    def keys(self) -> Rule[None, Iterable[K]]:
        return self._source.keys()

    def compute(self, q: Q, /) -> Step[V]:
        w = yield from fetch(self._source, q)
        return self._fn(w)


class MapNSeries[Q: Hashable, K: Key, W, V](Series[Q, K, V]):
    """A series whose every answer combines source answers at the same query.

    Query resolution is delegated independently to every source. ``merge_keys``
    only constructs the derived series' public domain; it is not involved when
    answering a query.
    """

    def __init__(
        self,
        name: str,
        sources: SeriesSources[Q, K, W],
        fn: Callable[[tuple[W, ...]], V],
        *,
        merge_keys: Callable[[tuple[Iterable[K], ...]], Iterable[K]],
    ) -> None:
        if not sources:
            raise ValueError("MapNSeries requires at least one source")
        super().__init__(name)
        self._sources = sources
        self._fn = fn
        self._keys: Rule[None, Iterable[K]] = _MapNKeys(name, sources, merge_keys)

    def keys(self) -> Rule[None, Iterable[K]]:
        return self._keys

    def compute(self, q: Q, /) -> Step[V]:
        values: list[W] = []
        for source in self._sources:
            values.append((yield from fetch(source, q)))
        return self._fn(tuple(values))


class Map2Series[Q: Hashable, K: Key, W1, W2, V](Series[Q, K, V]):
    """Combine two series at the same query; left and right answer types may differ.

    ``merge_keys`` only constructs the public domain; it is not used when
    answering a query.
    """

    def __init__(
        self,
        name: str,
        left: Series[Q, K, W1],
        right: Series[Q, K, W2],
        fn: Callable[[W1, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[K], ...]], Iterable[K]],
    ) -> None:
        super().__init__(name)
        self._left = left
        self._right = right
        self._fn = fn
        self._keys: Rule[None, Iterable[K]] = _MapNKeys(name, (left, right), merge_keys)

    def keys(self) -> Rule[None, Iterable[K]]:
        return self._keys

    def compute(self, q: Q, /) -> Step[V]:
        a = yield from fetch(self._left, q)
        b = yield from fetch(self._right, q)
        return self._fn(a, b)


class GridSeries[Q: Hashable, K: Key, V, W](Series[Q, K, W]):
    """Series backed by a lazy stream of ``(K, Step[V] | V)`` cells.

    ``cells`` is called once per context (via the internal cells rule) so each
    context gets fresh ``Step`` generators. ``query`` scans that stream for a
    given ``q``, forcing only the steps it needs.
    """

    def __init__(
        self,
        name: str,
        cells: Callable[[], Iterable[tuple[K, Step[V] | V]]],
        query: QueryFn[Q, K, V, W],
    ) -> None:
        super().__init__(name)
        self._cells: Rule[None, Iterable[tuple[K, Step[V] | V]]] = _Cells(name, cells)
        self._keys: Rule[None, Iterable[K]] = _GridKeys(name, self._cells)
        self._query = query

    def keys(self) -> Rule[None, Iterable[K]]:
        return self._keys

    def compute(self, q: Q, /) -> Step[W]:
        cells = yield from fetch(self._cells, None)
        return (yield from _as_step(self._query(q, cells)))


# ---------- internal glue ----------


class _Cells[K: Key, V](Rule[None, Iterable[tuple[K, Step[V] | V]]]):
    """Per-context cell stream: one Replayable buffer of ``(K, Step|V)`` pairs."""

    def __init__(
        self,
        name: str,
        cells: Callable[[], Iterable[tuple[K, Step[V] | V]]],
    ) -> None:
        super().__init__(f"{name}.cells")
        self._cells = cells

    def compute(self, key: None) -> Iterable[tuple[K, Step[V] | V]]:
        return Replayable(_ascending_pairs(self._cells()))


class _GridKeys[K: Key, V](Rule[None, Iterable[K]]):
    """Domain projected from cells; ``fetch(_cells)`` records the dependency."""

    def __init__(
        self,
        name: str,
        cells: Rule[None, Iterable[tuple[K, Step[V] | V]]],
    ) -> None:
        super().__init__(f"{name}.keys")
        self._cells = cells

    def compute(self, key: None) -> Step[Iterable[K]]:
        pairs = yield from fetch(self._cells, None)
        return _KeyProj(pairs)


class _KeyProj[K: Key, V](Iterable[K]):
    """Re-iterable key view over a shared pairs buffer."""

    def __init__(self, pairs: Iterable[tuple[K, Step[V] | V]]) -> None:
        self._pairs = pairs

    def __iter__(self) -> Iterator[K]:
        for k, _ in self._pairs:
            yield k


class _MapNKeys[Q: Hashable, K: Key](Rule[None, Iterable[K]]):
    """Demandable, replayable domain derived from several source domains."""

    def __init__(
        self,
        name: str,
        sources: tuple[Series[Q, K, Any], *tuple[Series[Q, K, Any], ...]],
        merge: Callable[[tuple[Iterable[K], ...]], Iterable[K]],
    ) -> None:
        super().__init__(f"{name}.keys")
        self._sources = sources
        self._merge = merge

    def compute(self, key: None, /) -> Step[Iterable[K]]:
        domains: list[Iterable[K]] = []
        for source in self._sources:
            domains.append((yield from fetch(source.keys(), None)))
        return Replayable(_ascending(self._merge(tuple(domains))))


def _ascending[K: Key](source: Iterable[K]) -> Iterator[K]:
    """Yield from ``source``, raising if consecutive keys are not strictly ascending."""
    prev: K | None = None
    for k in source:
        if prev is not None and not prev < k:
            raise ValueError(f"keys must be strictly ascending: got {prev!r} then {k!r}")
        prev = k
        yield k


def _ascending_pairs[K: Key, V](
    source: Iterable[tuple[K, Step[V] | V]],
) -> Iterator[tuple[K, Step[V] | V]]:
    prev: K | None = None
    for k, v in source:
        if prev is not None and not prev < k:
            raise ValueError(f"keys must be strictly ascending: got {prev!r} then {k!r}")
        prev = k
        yield (k, v)


def _as_step[V](value: Step[V] | V) -> Step[V]:
    """Normalize plain-vs-generator return values."""
    if isinstance(value, Generator):
        return value

    def completed() -> Step[V]:
        if False:
            yield
        return value

    return completed()
