# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Hashable, Iterable, Iterator, Sequence
from typing import Any, ClassVar, Protocol, Self, TypeIs, final

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


type Keys[K: Key] = Iterable[K]
"""Contract: strictly ascending (each key entirely before the next, hence
disjoint); possibly infinite; replayable (safe to re-iterate)."""


# ---------- missing values ----------


@final
class _NaType:
    """Type of the `Na` singleton; do not instantiate directly."""

    __slots__: tuple[()] = ()
    _instance: ClassVar[_NaType | None] = None

    def __new__(cls) -> _NaType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "Na"

    def __bool__(self) -> bool:
        raise TypeError("Na has no boolean value; test with `isna(value)` or `value is Na`")

    def __reduce__(self) -> str:
        return "Na"  # pickle/copy by module reference, preserving identity


Na: _NaType = _NaType()
"""Singleton 'no value'. Misses are values, never exceptions."""

type Maybe[V] = V | _NaType


def isna[V](value: Maybe[V]) -> TypeIs[_NaType]:
    """True if `value` is `Na`; narrows `Maybe[V]` to `V` when false."""
    return value is Na


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


class Series[Q: Hashable, K: Key, V, W](Rule[Q, W], ABC):
    """A rule with an explicit domain and packaged query semantics.

    Public surface: ``demand(self, q)`` and ``self.keys``. Values are readable
    only through queries; the grid is private.

    Law (grid identity): for every k in keys, querying at k returns that
    cell's value exactly.
    """

    def __init__(self, name: str, keys: Rule[None, Keys[K]] | Callable[[], Iterable[K]]):
        super().__init__(name)
        self.keys: Rule[None, Keys[K]] = (
            keys if isinstance(keys, Rule) else _KeysCell(name, keys)
        )  # pass an existing series' keys rule to share a domain definitionally
        self._cells: Rule[K, Maybe[V]] = _Cells(name, self)

    # ---- subclass contract (per kind: FlowSeries, PointSeries, ...) ----

    @abstractmethod
    def _value_at(self, key: K) -> Step[V] | V:
        """Grid definition; may assume key is covered.

        Recurrences: ``fetch(self._cells, prior_k)``. Query-flavored self-reference:
        ``fetch(self, q)``. Other rules/series: fetch their public face.
        """

    @abstractmethod
    def _select(self, keys: Keys[K], q: Q) -> Sequence[K]:
        """Pure. Grid keys relevant to ``q`` (overlap, bracketing, ...).

        Early-terminating scan of an ascending, possibly infinite stream. May
        return keys outside the domain (their cells resolve to ``Na``);
        whichever convention a kind picks, its ``_reduce`` must expect it.
        """

    @abstractmethod
    def _reduce(self, q: Q, items: Sequence[tuple[K, Maybe[V]]]) -> W:
        """Pure. Combine fetched cells into the answer.

        Owns the policy for misses and partial coverage (``q`` not spanned by
        selected keys).
        """

    # ---- final template ----

    def compute(self, q: Q, /) -> Step[W]:
        ks = yield from fetch(self.keys, None)
        items: list[tuple[K, Maybe[V]]] = []
        for k in self._select(ks, q):
            v = yield from fetch(self._cells, k)
            items.append((k, v))
        return self._reduce(q, items)


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


class _Cells[K: Key, V](Rule[K, Maybe[V]]):
    """Internal grid; total (uncovered -> Na).

    Reachable only via the owning series object — privacy is structural, not
    conventional.
    """

    def __init__(self, name: str, series: Series[Any, K, V, Any]):
        super().__init__(f"{name}.cells")
        self._series = series

    def compute(self, key: K) -> Step[Maybe[V]]:
        ks = yield from fetch(self._series.keys, None)
        if not _covered(ks, key):
            return Na
        return (yield from _as_step(self._series._value_at(key)))


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
