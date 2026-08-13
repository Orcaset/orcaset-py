# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

import operator
from abc import ABC
from collections.abc import Callable, Iterable
from typing import Any

from orcaset.maybe import Maybe, map2_some, map_some
from orcaset.period import Period, period_union
from orcaset.rule import Rule, Step, get, get_at
from orcaset.series import (
    BaseSeries,
    CellsFn,
    QueryFn,
    _as_step,
    _Cells,
    _ContinueFrom,
    _ContinueKeys,
    _GridKeys,
    _MapNKeys,
)


def _identity[T](value: T) -> T:
    return value


class PeriodSeriesBase[W](BaseSeries[Period, Period, W], ABC):
    """Period-keyed series surface: ``map`` / ``map2`` / Na-aware arithmetic.

    Cell-backed grids (``PeriodSeries``) and derived combinators share this type
    so operator chaining and ``isinstance`` checks stay closed over the surface.
    """

    def map[V](self, name: str, fn: Callable[[W], V]) -> PeriodMapSeries[W, V]:
        return PeriodMapSeries(name, self, fn)

    def map2[W2, V](
        self,
        name: str,
        other: BaseSeries[Period, Period, W2],
        fn: Callable[[W, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[Period], ...]], Iterable[Period]] | None = None,
    ) -> PeriodMap2Series[W, W2, V]:
        """Combine with any ``Period``-keyed series; domain defaults to ``period_union``."""
        return PeriodMap2Series(
            name,
            self,
            other,
            fn,
            merge_keys=period_union if merge_keys is None else merge_keys,
        )

    def extend_with(
        self,
        name: str,
        continuation: Callable[[Period], PeriodSeriesBase[W]],
        combine: Callable[[W, W], W],
    ) -> PeriodExtendSeries[W]:
        """Answer from ``self`` until its domain is exhausted, then from ``continuation``.

        ``continuation`` receives the last base ``Period``. ``combine`` folds the
        two answers when a query spans that last ``end``.
        """
        return PeriodExtendSeries(name, self, continuation, combine)

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


class PeriodMapSeries[W, V](PeriodSeriesBase[V]):
    """Map resolved query answers while preserving a period-keyed surface.

    ``keys()`` aliases the source domain. ``fn`` receives the source's resolved
    answer at each query, including any miss sentinel returned by its query.
    """

    def __init__(
        self,
        name: str,
        source: BaseSeries[Period, Period, W],
        fn: Callable[[W], V],
    ) -> None:
        super().__init__(name)
        self._source = source
        self._fn = fn

    def keys(self) -> Rule[Iterable[Period]]:
        return self._source.keys()

    def compute(self, q: Period, /) -> Step[V]:
        w = yield from get_at(self._source, q)
        return self._fn(w)


class PeriodMap2Series[W1, W2, V](PeriodSeriesBase[V]):
    """Combine two period-keyed series' resolved answers at the same query.

    ``merge_keys`` constructs only the advertised domain; it does not affect
    query computation. The default ``period_union`` may advertise split
    fragments that a source's own query answers with ``Na``.
    """

    def __init__(
        self,
        name: str,
        left: BaseSeries[Period, Period, W1],
        right: BaseSeries[Period, Period, W2],
        fn: Callable[[W1, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[Period], ...]], Iterable[Period]] | None = None,
    ) -> None:
        super().__init__(name)
        self._left = left
        self._right = right
        self._fn = fn
        self._keys: Rule[Iterable[Period]] = _MapNKeys(
            name,
            (left, right),
            period_union if merge_keys is None else merge_keys,
        )

    def keys(self) -> Rule[Iterable[Period]]:
        return self._keys

    def compute(self, q: Period, /) -> Step[V]:
        a = yield from get_at(self._left, q)
        b = yield from get_at(self._right, q)
        return self._fn(a, b)


class PeriodExtendSeries[W](PeriodSeriesBase[W]):
    """Answer from ``base`` until it is exhausted, then from a continuation series.

    ``continuation`` receives the last base ``Period``. Queries that end inside
    the base never materialize it. Queries that cross the last ``end`` are split
    there; each side is answered with that source's own query, then ``combine``.
    The base domain must be finite.
    """

    def __init__(
        self,
        name: str,
        base: PeriodSeriesBase[W],
        continuation: Callable[[Period], PeriodSeriesBase[W]],
        combine: Callable[[W, W], W],
    ) -> None:
        super().__init__(name)
        self._base = base
        self._combine = combine
        self._continuation = _ContinueFrom(name, base, continuation)
        self._keys = _ContinueKeys(name, base, self._continuation)

    @classmethod
    def define[W2](
        cls,
        name: str,
        base: PeriodSeriesBase[W2],
        combine: Callable[[W2, W2], W2],
    ) -> Callable[[Callable[[Period], PeriodSeriesBase[W2]]], PeriodExtendSeries[W2]]:
        """Decorator: build a ``PeriodExtendSeries`` from a continuation factory."""

        def decorator(
            continuation: Callable[[Period], PeriodSeriesBase[W2]],
        ) -> PeriodExtendSeries[W2]:
            return PeriodExtendSeries(name, base, continuation, combine)

        return decorator

    def keys(self) -> Rule[Iterable[Period]]:
        return self._keys

    def compute(self, q: Period, /) -> Step[W]:
        last: Period | None = None
        for k in (yield from get(self._base.keys())):
            if k.end >= q.end:
                return (yield from get_at(self._base, q))
            last = k
        if last is None:
            raise ValueError(f"{self.name}: base series is empty")

        cont = yield from get(self._continuation)
        if q.start < last.end:
            left = yield from get_at(self._base, Period(q.start, last.end))
            right = yield from get_at(cont, Period(last.end, q.end))
            return self._combine(left, right)
        return (yield from get_at(cont, q))
