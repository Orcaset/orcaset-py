# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

import operator
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Hashable, Iterable, Iterator
from datetime import date
from itertools import chain
from typing import Any, Protocol, Self, cast

from orcaset.maybe import Maybe, map2_some, map_some
from orcaset.period import Period, date_union, period_union
from orcaset.rule import Demand, KeyedRule, Rule, Step, get, get_at

# ---------- keys ----------


class Key(Hashable, Protocol):
    """Series key: hashable (cell identity) and comparable (lazy scans).

    ``a < b`` means "a is entirely before b". The order need not be total:
    keys that overlap (e.g. overlapping ``Period``s) may be mutually
    incomparable. Scans only require that domain streams are strictly
    ascending, so anything entirely past a probe stays past it.
    """

    def __lt__(self, other: Self, /) -> bool: ...


type CellFactory[V] = Callable[[], Step[V] | V]
"""Builds a fresh ``Step`` (or plain value) each time a cell is computed."""

type CellStream[K: Key, V] = Generator[
    Demand[Any] | tuple[K, V | CellFactory[V]],
    Any,
    Iterable[tuple[K, V | CellFactory[V]]] | None,
]
"""A cell-producing generator: demand rules, then yield or return pairs.

Yields ``Demand``s (via ``get``/``get_at``) and/or ``(key, value | factory)``
pairs. All demands must precede the first pair — once a pair is seen the
remainder is driven as a plain pairs iterator. A pure ``Step`` shape may
``return`` the pairs iterable instead of yielding pairs.
"""

type CellsFn[K: Key, V] = Callable[
    [],
    CellStream[K, V] | Iterable[tuple[K, V | CellFactory[V]]],
]
"""Builds the cell stream for a ``Series``.

Three shapes are accepted:

- Ordinary callables return an iterable of ``(key, value | factory)`` pairs.
- Generator functions yield those pairs directly.
- Generator functions may also demand other rules with ``get``/``get_at``
  before their first pair (or ``return`` the pairs iterable) — annotate these
  as ``CellStream``.

``_Cells`` drives the factory and branches on each yielded item, so no static
distinction is needed. All demands must finish before the first pair — once a
pair is seen the remainder is driven as a plain pairs iterator.
"""

type QueryFn[Q, K: Key, V, W] = Callable[
    [Q, Iterable[tuple[K, Rule[V]]]],
    Step[W] | W,
]
"""Fold a query over a lazy cell stream into an answer.

Each cell is a ``Rule[V]`` — force with ``yield from get(cell)``. May scan
without forcing every cell (early-terminate, skip). Fixed per series at
construction so a series cannot be read under another convention.
"""


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


class BaseSeries[Q: Hashable, K: Key, W](KeyedRule[Q, W], ABC):
    """A demandable rule with an explicit time domain.

    Public surface: ``compute`` (via ``KeyedRule``) and ``keys()``. Values are only
    reachable through ``compute``, so every answer is dependency-tracked.
    """

    @abstractmethod
    def keys(self) -> Rule[Iterable[K]]:
        """Demandable ascending domain (strictly ascending, possibly infinite)."""
        ...

    def map[V](self, name: str, fn: Callable[[W], V]) -> BaseSeries[Q, K, V]:
        """Derived series answering ``fn(self answered at q)`` for every query.

        ``fn`` sees the raw answer (typically ``Maybe``) and owns the miss policy.
        Domain aliases ``self.keys()``.
        """
        return MapSeries(name, self, fn)

    def map2[W2, V](
        self,
        name: str,
        other: BaseSeries[Q, K, W2],
        fn: Callable[[W, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[K], ...]], Iterable[K]],
    ) -> BaseSeries[Q, K, V]:
        """Combine ``self`` and ``other`` at each query via ``fn``.

        Sources may have different answer types. ``merge_keys`` builds the
        derived domain only.
        """
        return Map2Series(name, self, other, fn, merge_keys=merge_keys)


class MapSeries[Q: Hashable, K: Key, W, V](BaseSeries[Q, K, V]):
    """A series whose every answer is ``fn(source answered at q)``.

    Query resolution is fully delegated to the source; ``keys()`` returns the
    source domain rule so both share one buffer per context and traces show the
    dependency.
    """

    def __init__(self, name: str, source: BaseSeries[Q, K, W], fn: Callable[[W], V]) -> None:
        super().__init__(name)
        self._source = source
        self._fn = fn

    def keys(self) -> Rule[Iterable[K]]:
        return self._source.keys()

    def compute(self, q: Q, /) -> Step[V]:
        w = yield from get_at(self._source, q)
        return self._fn(w)


class MapNSeries[Q: Hashable, K: Key, W, V](BaseSeries[Q, K, V]):
    """A series whose every answer combines source answers at the same query.

    Query resolution is delegated independently to every source. An empty
    ``sources`` tuple is allowed: ``compute`` answers ``fn(())`` and
    ``merge_keys`` receives ``()``. ``merge_keys`` only constructs the derived
    series' public domain; it is not involved when answering a query.
    """

    def __init__(
        self,
        name: str,
        sources: tuple[BaseSeries[Q, K, W], ...],
        fn: Callable[[tuple[W, ...]], V],
        *,
        merge_keys: Callable[[tuple[Iterable[K], ...]], Iterable[K]],
    ) -> None:
        super().__init__(name)
        self._sources = sources
        self._fn = fn
        self._keys: Rule[Iterable[K]] = _MapNKeys(name, sources, merge_keys)

    def keys(self) -> Rule[Iterable[K]]:
        return self._keys

    def compute(self, q: Q, /) -> Step[V]:
        values: list[W] = []
        for source in self._sources:
            values.append((yield from get_at(source, q)))
        return self._fn(tuple(values))


class Map2Series[Q: Hashable, K: Key, W1, W2, V](BaseSeries[Q, K, V]):
    """Combine two series at the same query; left and right answer types may differ.

    ``merge_keys`` only constructs the public domain; it is not used when
    answering a query.
    """

    def __init__(
        self,
        name: str,
        left: BaseSeries[Q, K, W1],
        right: BaseSeries[Q, K, W2],
        fn: Callable[[W1, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[K], ...]], Iterable[K]],
    ) -> None:
        super().__init__(name)
        self._left = left
        self._right = right
        self._fn = fn
        self._keys: Rule[Iterable[K]] = _MapNKeys(name, (left, right), merge_keys)

    def keys(self) -> Rule[Iterable[K]]:
        return self._keys

    def compute(self, q: Q, /) -> Step[V]:
        a = yield from get_at(self._left, q)
        b = yield from get_at(self._right, q)
        return self._fn(a, b)


class Series[Q: Hashable, K: Key, V, W](BaseSeries[Q, K, W]):
    """Series backed by a lazy stream of ``(K, Rule[V])`` cells.

    ``cells`` is a zero-arg factory yielding or returning ``(key, value | factory)``
    pairs, where each value is plain or a factory ``() -> Step[V] | V``. It may
    also be a ``Step`` that demands other rules before its first pair; see
    ``CellsFn`` for the accepted shapes. Each cell is wrapped as a ``Rule`` so
    forcing is context-memoized and dependency-tracked. Live generators as cell
    *values* are rejected — pass a factory instead.

    Prefer ``PeriodSeries`` / ``DateSeries`` when ``Q`` and ``K`` are ``Period`` or
    ``date`` — those add Na-propagating arithmetic and a fixed domain union.
    Derived period/date series are typed as ``PeriodSeriesBase`` / ``DateSeriesBase``.
    """

    def __init__(
        self,
        name: str,
        cells: CellsFn[K, V],
        query: QueryFn[Q, K, V, W],
    ) -> None:
        super().__init__(name)
        self._cells: Rule[Iterable[tuple[K, Rule[V]]]] = _Cells(name, cells)
        self._keys: Rule[Iterable[K]] = _GridKeys(name, self._cells)
        self._query = query

    @classmethod
    def define[
        Q2: Hashable,
        K2: Key,
        V2,
        W2,
    ](
        cls,
        name: str,
        query: QueryFn[Q2, K2, V2, W2],
    ) -> Callable[[CellsFn[K2, V2]], Series[Q2, K2, V2, W2]]:
        """Decorator: build a ``Series`` from a cells factory.

        Arguments are ``name`` then ``query``. The decorated function becomes
        the series value (not the cells callable).
        """

        def decorator(cells: CellsFn[K2, V2]) -> Series[Q2, K2, V2, W2]:
            build = cast(
                Callable[
                    [str, CellsFn[K2, V2], QueryFn[Q2, K2, V2, W2]],
                    Series[Q2, K2, V2, W2],
                ],
                cls,
            )
            return build(name, cells, query)

        return decorator

    def keys(self) -> Rule[Iterable[K]]:
        return self._keys

    def compute(self, q: Q, /) -> Step[W]:
        cells = yield from get(self._cells)
        return (yield from _as_step(self._query(q, cells)))


# ---------- period / date series ----------


def _identity[T](value: T) -> T:
    return value


class PeriodSeriesBase[W](BaseSeries[Period, Period, W], ABC):
    """Period-keyed series surface: ``map`` / ``map2`` / Na-aware arithmetic.

    Cell-backed grids (``PeriodSeries``) and derived combinators share this type
    so operator chaining and ``isinstance`` checks stay closed over the surface.
    """

    def map[V](self, name: str, fn: Callable[[W], V]) -> PeriodSeriesBase[V]:
        return _PeriodMapSeries(name, self, fn)

    def map2[W2, V](
        self,
        name: str,
        other: BaseSeries[Period, Period, W2],
        fn: Callable[[W, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[Period], ...]], Iterable[Period]] | None = None,
    ) -> PeriodSeriesBase[V]:
        """Combine with any ``Period``-keyed series; domain defaults to ``period_union``."""
        return _PeriodMap2Series(
            name,
            self,
            other,
            fn,
            merge_keys=period_union if merge_keys is None else merge_keys,
        )

    def named(self, name: str) -> PeriodSeriesBase[W]:
        """Identity-mapped series with a new display name."""
        return self.map(name, _identity)

    def __add__[W1: Maybe[float], W2: Maybe[float]](
        self: PeriodSeriesBase[W1], other: PeriodSeriesBase[W2] | float
    ) -> PeriodSeriesBase[Maybe[float]]:
        return self._binop(other, operator.add, "+")

    def __radd__[W1: Maybe[float]](
        self: PeriodSeriesBase[W1], other: float
    ) -> PeriodSeriesBase[Maybe[float]]:
        return self._rbinop(other, operator.add, "+")

    def __sub__[W1: Maybe[float], W2: Maybe[float]](
        self: PeriodSeriesBase[W1], other: PeriodSeriesBase[W2] | float
    ) -> PeriodSeriesBase[Maybe[float]]:
        return self._binop(other, operator.sub, "-")

    def __rsub__[W1: Maybe[float]](
        self: PeriodSeriesBase[W1], other: float
    ) -> PeriodSeriesBase[Maybe[float]]:
        return self._rbinop(other, operator.sub, "-")

    def __mul__[W1: Maybe[float], W2: Maybe[float]](
        self: PeriodSeriesBase[W1], other: PeriodSeriesBase[W2] | float
    ) -> PeriodSeriesBase[Maybe[float]]:
        return self._binop(other, operator.mul, "*")

    def __rmul__[W1: Maybe[float]](
        self: PeriodSeriesBase[W1], other: float
    ) -> PeriodSeriesBase[Maybe[float]]:
        return self._rbinop(other, operator.mul, "*")

    def __truediv__[W1: Maybe[float], W2: Maybe[float]](
        self: PeriodSeriesBase[W1], other: PeriodSeriesBase[W2] | float
    ) -> PeriodSeriesBase[Maybe[float]]:
        return self._binop(other, operator.truediv, "/")

    def __rtruediv__[W1: Maybe[float]](
        self: PeriodSeriesBase[W1], other: float
    ) -> PeriodSeriesBase[Maybe[float]]:
        return self._rbinop(other, operator.truediv, "/")

    def __neg__[W1: Maybe[float]](self: PeriodSeriesBase[W1]) -> PeriodSeriesBase[Maybe[float]]:
        return self.map(f"(-{self.name})", map_some(operator.neg))

    def __pos__[W1: Maybe[float]](self: PeriodSeriesBase[W1]) -> PeriodSeriesBase[Maybe[float]]:
        return self.map(f"(+{self.name})", map_some(operator.pos))

    def _binop(
        self,
        other: object,
        op: Callable[[Any, Any], Any],
        sym: str,
    ) -> PeriodSeriesBase[Any]:
        if isinstance(other, PeriodSeriesBase):
            return self.map2(f"({self.name} {sym} {other.name})", other, map2_some(op))
        if isinstance(other, (int, float)):
            return self.map(f"({self.name} {sym} {other!r})", map_some(lambda w: op(w, other)))
        return NotImplemented

    def _rbinop(
        self,
        other: object,
        op: Callable[[Any, Any], Any],
        sym: str,
    ) -> PeriodSeriesBase[Any]:
        if isinstance(other, (int, float)):
            return self.map(f"({other!r} {sym} {self.name})", map_some(lambda w: op(other, w)))
        return NotImplemented


class DateSeriesBase[W](BaseSeries[date, date, W], ABC):
    """Date-keyed series surface: ``map`` / ``map2`` / Na-aware arithmetic.

    Cell-backed grids (``DateSeries``) and derived combinators share this type
    so operator chaining and ``isinstance`` checks stay closed over the surface.
    """

    def map[V](self, name: str, fn: Callable[[W], V]) -> DateSeriesBase[V]:
        return _DateMapSeries(name, self, fn)

    def map2[W2, V](
        self,
        name: str,
        other: BaseSeries[date, date, W2],
        fn: Callable[[W, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[date], ...]], Iterable[date]] | None = None,
    ) -> DateSeriesBase[V]:
        """Combine with any ``date``-keyed series; domain defaults to ``date_union``."""
        return _DateMap2Series(
            name,
            self,
            other,
            fn,
            merge_keys=date_union if merge_keys is None else merge_keys,
        )

    def named(self, name: str) -> DateSeriesBase[W]:
        """Identity-mapped series with a new display name."""
        return self.map(name, _identity)

    def __add__[W1: Maybe[float], W2: Maybe[float]](
        self: DateSeriesBase[W1], other: DateSeriesBase[W2] | float
    ) -> DateSeriesBase[Maybe[float]]:
        return self._binop(other, operator.add, "+")

    def __radd__[W1: Maybe[float]](
        self: DateSeriesBase[W1], other: float
    ) -> DateSeriesBase[Maybe[float]]:
        return self._rbinop(other, operator.add, "+")

    def __sub__[W1: Maybe[float], W2: Maybe[float]](
        self: DateSeriesBase[W1], other: DateSeriesBase[W2] | float
    ) -> DateSeriesBase[Maybe[float]]:
        return self._binop(other, operator.sub, "-")

    def __rsub__[W1: Maybe[float]](
        self: DateSeriesBase[W1], other: float
    ) -> DateSeriesBase[Maybe[float]]:
        return self._rbinop(other, operator.sub, "-")

    def __mul__[W1: Maybe[float], W2: Maybe[float]](
        self: DateSeriesBase[W1], other: DateSeriesBase[W2] | float
    ) -> DateSeriesBase[Maybe[float]]:
        return self._binop(other, operator.mul, "*")

    def __rmul__[W1: Maybe[float]](
        self: DateSeriesBase[W1], other: float
    ) -> DateSeriesBase[Maybe[float]]:
        return self._rbinop(other, operator.mul, "*")

    def __truediv__[W1: Maybe[float], W2: Maybe[float]](
        self: DateSeriesBase[W1], other: DateSeriesBase[W2] | float
    ) -> DateSeriesBase[Maybe[float]]:
        return self._binop(other, operator.truediv, "/")

    def __rtruediv__[W1: Maybe[float]](
        self: DateSeriesBase[W1], other: float
    ) -> DateSeriesBase[Maybe[float]]:
        return self._rbinop(other, operator.truediv, "/")

    def __neg__[W1: Maybe[float]](self: DateSeriesBase[W1]) -> DateSeriesBase[Maybe[float]]:
        return self.map(f"(-{self.name})", map_some(operator.neg))

    def __pos__[W1: Maybe[float]](self: DateSeriesBase[W1]) -> DateSeriesBase[Maybe[float]]:
        return self.map(f"(+{self.name})", map_some(operator.pos))

    def _binop(
        self,
        other: object,
        op: Callable[[Any, Any], Any],
        sym: str,
    ) -> DateSeriesBase[Any]:
        if isinstance(other, DateSeriesBase):
            return self.map2(f"({self.name} {sym} {other.name})", other, map2_some(op))
        if isinstance(other, (int, float)):
            return self.map(f"({self.name} {sym} {other!r})", map_some(lambda w: op(w, other)))
        return NotImplemented

    def _rbinop(
        self,
        other: object,
        op: Callable[[Any, Any], Any],
        sym: str,
    ) -> DateSeriesBase[Any]:
        if isinstance(other, (int, float)):
            return self.map(f"({other!r} {sym} {self.name})", map_some(lambda w: op(other, w)))
        return NotImplemented


class PeriodSeries[W](PeriodSeriesBase[W]):
    """Cell-backed series with ``Q = K = Period`` and ``period_union`` merges.

    Supports Na-propagating arithmetic via ``PeriodSeriesBase``. Derived series
    (``map``, ``map2``, operators) are ``PeriodSeriesBase``, not cell-backed grids.
    """

    def __init__[V](
        self,
        name: str,
        cells: CellsFn[Period, V],
        query: QueryFn[Period, Period, V, W],
    ) -> None:
        super().__init__(name)
        self._cells: Rule[Iterable[tuple[Period, Rule[Any]]]] = _Cells(name, cells)
        self._keys: Rule[Iterable[Period]] = _GridKeys(name, self._cells)
        self._query: QueryFn[Period, Period, Any, W] = query

    @classmethod
    def define[V, W2](
        cls,
        name: str,
        query: QueryFn[Period, Period, V, W2],
    ) -> Callable[[CellsFn[Period, V]], PeriodSeries[W2]]:
        """Decorator: build a ``PeriodSeries`` from a cells factory."""

        def decorator(cells: CellsFn[Period, V]) -> PeriodSeries[W2]:
            return PeriodSeries(name, cells, query)

        return decorator

    def keys(self) -> Rule[Iterable[Period]]:
        return self._keys

    def compute(self, q: Period, /) -> Step[W]:
        cells = yield from get(self._cells)
        return (yield from _as_step(self._query(q, cells)))


class DateSeries[W](DateSeriesBase[W]):
    """Cell-backed series with ``Q = K = date`` and ``date_union`` merges.

    Supports Na-propagating arithmetic via ``DateSeriesBase``. Derived series
    (``map``, ``map2``, operators) are ``DateSeriesBase``, not cell-backed grids.
    """

    def __init__[V](
        self,
        name: str,
        cells: CellsFn[date, V],
        query: QueryFn[date, date, V, W],
    ) -> None:
        super().__init__(name)
        self._cells: Rule[Iterable[tuple[date, Rule[Any]]]] = _Cells(name, cells)
        self._keys: Rule[Iterable[date]] = _GridKeys(name, self._cells)
        self._query: QueryFn[date, date, Any, W] = query

    @classmethod
    def define[V, W2](
        cls,
        name: str,
        query: QueryFn[date, date, V, W2],
    ) -> Callable[[CellsFn[date, V]], DateSeries[W2]]:
        """Decorator: build a ``DateSeries`` from a cells factory."""

        def decorator(cells: CellsFn[date, V]) -> DateSeries[W2]:
            return DateSeries(name, cells, query)

        return decorator

    def keys(self) -> Rule[Iterable[date]]:
        return self._keys

    def compute(self, q: date, /) -> Step[W]:
        cells = yield from get(self._cells)
        return (yield from _as_step(self._query(q, cells)))


class _PeriodMapSeries[W, V](PeriodSeriesBase[V]):
    """Answers ``fn(source answered at q)``; ``keys()`` aliases the source domain."""

    def __init__(self, name: str, source: PeriodSeriesBase[W], fn: Callable[[W], V]) -> None:
        super().__init__(name)
        self._source = source
        self._fn = fn

    def keys(self) -> Rule[Iterable[Period]]:
        return self._source.keys()

    def compute(self, q: Period, /) -> Step[V]:
        w = yield from get_at(self._source, q)
        return self._fn(w)


class _PeriodMap2Series[W1, W2, V](PeriodSeriesBase[V]):
    """Combines two ``Period``-keyed series at the same query."""

    def __init__(
        self,
        name: str,
        left: PeriodSeriesBase[W1],
        right: BaseSeries[Period, Period, W2],
        fn: Callable[[W1, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[Period], ...]], Iterable[Period]],
    ) -> None:
        super().__init__(name)
        self._left = left
        self._right = right
        self._fn = fn
        self._keys: Rule[Iterable[Period]] = _MapNKeys(name, (left, right), merge_keys)

    def keys(self) -> Rule[Iterable[Period]]:
        return self._keys

    def compute(self, q: Period, /) -> Step[V]:
        a = yield from get_at(self._left, q)
        b = yield from get_at(self._right, q)
        return self._fn(a, b)


class _DateMapSeries[W, V](DateSeriesBase[V]):
    """Answers ``fn(source answered at q)``; ``keys()`` aliases the source domain."""

    def __init__(self, name: str, source: DateSeriesBase[W], fn: Callable[[W], V]) -> None:
        super().__init__(name)
        self._source = source
        self._fn = fn

    def keys(self) -> Rule[Iterable[date]]:
        return self._source.keys()

    def compute(self, q: date, /) -> Step[V]:
        w = yield from get_at(self._source, q)
        return self._fn(w)


class _DateMap2Series[W1, W2, V](DateSeriesBase[V]):
    """Combines two ``date``-keyed series at the same query."""

    def __init__(
        self,
        name: str,
        left: DateSeriesBase[W1],
        right: BaseSeries[date, date, W2],
        fn: Callable[[W1, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[date], ...]], Iterable[date]],
    ) -> None:
        super().__init__(name)
        self._left = left
        self._right = right
        self._fn = fn
        self._keys: Rule[Iterable[date]] = _MapNKeys(name, (left, right), merge_keys)

    def keys(self) -> Rule[Iterable[date]]:
        return self._keys

    def compute(self, q: date, /) -> Step[V]:
        a = yield from get_at(self._left, q)
        b = yield from get_at(self._right, q)
        return self._fn(a, b)


class MapItemsSeries[Q: Hashable, K: Key, V, W, A](BaseSeries[Q, K, A]):
    """Map each source key via ``fn(k, source)``, then query the derived stream.

    ``source`` must be ``BaseSeries[K, K, W]`` so domain keys are valid point queries.
    ``fn`` receives the key and source series so it can ``get_at`` for deps.
    ``keys()`` aliases ``source.keys()``.
    """

    def __init__(
        self,
        name: str,
        source: BaseSeries[K, K, W],
        fn: Callable[[K, BaseSeries[K, K, W]], Step[V] | V],
        query: QueryFn[Q, K, V, A],
    ) -> None:
        super().__init__(name)
        self._source = source
        self._cells: Rule[Iterable[tuple[K, Rule[V]]]] = _ItemCells(name, source, fn)
        self._query = query

    def keys(self) -> Rule[Iterable[K]]:
        return self._source.keys()

    def compute(self, q: Q, /) -> Step[A]:
        cells = yield from get(self._cells)
        return (yield from _as_step(self._query(q, cells)))


# ---------- internal glue ----------


class _CellRule[V](Rule[V]):
    """One memoized cell value, forced via ``get(cell)``."""

    def __init__(self, name: str, factory: CellFactory[V]) -> None:
        super().__init__(name)
        self._factory = factory

    def compute(self) -> Step[V]:
        return (yield from _as_step(self._factory()))


class _Cells[K: Key, V](Rule[Iterable[tuple[K, Rule[V]]]]):
    """Per-context cell stream: Replayable buffer of ``(K, Rule[V])``.

    The factory may return an iterable of pairs, be a generator that yields
    pairs, or be a ``Step`` that demands other rules before yielding/returning
    the pairs. The shapes are indistinguishable statically, so a generator
    result is driven one step at a time and branched on its first yield: a
    ``Demand`` means a ``Step``; a pair means a plain pairs iterator.
    """

    def __init__(self, name: str, cells: CellsFn[K, V]) -> None:
        super().__init__(f"{name}.cells")
        self._series_name = name
        self._cells = cells

    def compute(self) -> Step[Iterable[tuple[K, Rule[V]]]]:
        result = self._cells()
        if not isinstance(result, Generator):
            raw = result
            return Replayable(_cell_pairs(self._series_name, raw))

        it = cast(CellStream[K, V], result)
        to_send: Any = None
        while True:
            try:
                item = it.send(to_send)
            except StopIteration as done:
                if done.value is None:
                    return Replayable(_cell_pairs(self._series_name, ()))
                return Replayable(
                    _cell_pairs(
                        self._series_name, cast(Iterable[tuple[K, V | CellFactory[V]]], done.value)
                    )
                )
            if isinstance(item, Demand):
                to_send = yield item
                continue
            pairs = chain(
                [item],
                cast(Iterator[tuple[K, V | CellFactory[V]]], it),
            )
            return Replayable(_cell_pairs(self._series_name, pairs))


class _ItemCells[K: Key, W, V](Rule[Iterable[tuple[K, Rule[V]]]]):
    """Cell stream: for each source key, a rule that runs ``fn(k, source)``."""

    def __init__(
        self,
        name: str,
        source: BaseSeries[K, K, W],
        fn: Callable[[K, BaseSeries[K, K, W]], Step[V] | V],
    ) -> None:
        super().__init__(f"{name}.cells")
        self._series_name = name
        self._source = source
        self._fn = fn

    def compute(self) -> Step[Iterable[tuple[K, Rule[V]]]]:
        keys = yield from get(self._source.keys())

        def factories() -> Iterator[tuple[K, CellFactory[V]]]:
            for k in keys:

                def factory(src: K = k) -> Step[V]:
                    return (yield from _as_step(self._fn(src, self._source)))

                yield k, factory

        return Replayable(_cell_pairs(self._series_name, factories()))


class _GridKeys[K: Key, V](Rule[Iterable[K]]):
    """Domain projected from cells; ``get(_cells)`` records the dependency."""

    def __init__(
        self,
        name: str,
        cells: Rule[Iterable[tuple[K, Rule[V]]]],
    ) -> None:
        super().__init__(f"{name}.keys")
        self._cells = cells

    def compute(self) -> Step[Iterable[K]]:
        pairs = yield from get(self._cells)
        return _KeyProj(pairs)


class _KeyProj[K: Key, V](Iterable[K]):
    """Re-iterable key view over a shared pairs buffer."""

    def __init__(self, pairs: Iterable[tuple[K, Rule[V]]]) -> None:
        self._pairs = pairs

    def __iter__(self) -> Iterator[K]:
        for k, _ in self._pairs:
            yield k


class _MapNKeys[Q: Hashable, K: Key](Rule[Iterable[K]]):
    """Demandable, replayable domain derived from several source domains."""

    def __init__(
        self,
        name: str,
        sources: tuple[BaseSeries[Q, K, Any], ...],
        merge: Callable[[tuple[Iterable[K], ...]], Iterable[K]],
    ) -> None:
        super().__init__(f"{name}.keys")
        self._sources = sources
        self._merge = merge

    def compute(self) -> Step[Iterable[K]]:
        domains: list[Iterable[K]] = []
        for source in self._sources:
            domains.append((yield from get(source.keys())))
        return Replayable(_ascending(self._merge(tuple(domains))))


def _ascending[K: Key](source: Iterable[K]) -> Iterator[K]:
    """Yield from ``source``, raising if consecutive keys are not strictly ascending."""
    prev: K | None = None
    for k in source:
        if prev is not None and not prev < k:
            raise ValueError(f"keys must be strictly ascending: got {prev!r} then {k!r}")
        prev = k
        yield k


def _cell_pairs[K: Key, V](
    series_name: str,
    source: Iterable[tuple[K, V | CellFactory[V]]],
) -> Iterator[tuple[K, Rule[V]]]:
    prev: K | None = None
    for item in source:
        if isinstance(item, Demand):
            raise TypeError(
                f"series {series_name!r}: get/get_at demanded after the first cell "
                "pair was yielded; demand all dependencies before yielding pairs, "
                "or move the demand into a per-cell factory"
            )
        k, v = item
        if prev is not None and not prev < k:
            raise ValueError(f"keys must be strictly ascending: got {prev!r} then {k!r}")
        prev = k
        yield k, _CellRule(f"{series_name}@{k}", _as_factory(v))


def _as_factory[V](value: V | CellFactory[V]) -> CellFactory[V]:
    if isinstance(value, Generator):
        raise TypeError(
            "cell values must be plain values or factories () -> Step[V] | V, "
            "not live generators; use lambda: my_step() instead"
        )
    if callable(value):
        return value  # type: ignore[return-value]
    return lambda v=value: v


def _as_step[V](value: Step[V] | V) -> Step[V]:
    """Normalize plain-vs-generator return values."""
    if isinstance(value, Generator):
        return value

    def completed() -> Step[V]:
        if False:
            yield
        return value

    return completed()
