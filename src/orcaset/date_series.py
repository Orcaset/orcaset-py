# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

import operator
from abc import ABC
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

from orcaset.maybe import Maybe, map2_some, map_some
from orcaset.period import date_union
from orcaset.rule import RuleBase, Step, get, get_at
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


class DateSeriesBase[W](BaseSeries[date, date, W], ABC):
    """Date-keyed series surface: ``map`` / ``map2`` / Na-aware arithmetic.

    Cell-backed grids (``DateSeries``) and derived combinators share this type
    so operator chaining and ``isinstance`` checks stay closed over the surface.
    """

    def map[V](self, name: str, fn: Callable[[W], V]) -> DateMapSeries[W, V]:
        return DateMapSeries(name, self, fn)

    def map2[W2, V](
        self,
        name: str,
        other: BaseSeries[date, date, W2],
        fn: Callable[[W, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[date], ...]], Iterable[date]] | None = None,
    ) -> DateMap2Series[W, W2, V]:
        """Combine with any ``date``-keyed series; domain defaults to ``date_union``."""
        return DateMap2Series(
            name,
            self,
            other,
            fn,
            merge_keys=date_union if merge_keys is None else merge_keys,
        )

    def extend_with(
        self,
        name: str,
        continuation: Callable[[date], DateSeriesBase[W]],
    ) -> DateExtendSeries[W]:
        """Answer from ``self`` until ``continuation``'s domain begins.

        ``continuation`` receives the last base ``date`` and owns dates at or
        after its own first key. Point queries are not split: ``q`` is answered
        by the base while it is before the first continuation key (so an as-of
        base query carries forward across the seam), otherwise by the
        continuation.
        """
        return DateExtendSeries(name, self, continuation)

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
        self._cells: RuleBase[Iterable[tuple[date, RuleBase[Any]]]] = _Cells(name, cells)
        self._keys: RuleBase[Iterable[date]] = _GridKeys(name, self._cells)
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

    def keys(self) -> RuleBase[Iterable[date]]:
        return self._keys

    def compute(self, q: date, /) -> Step[W]:
        cells = yield from get(self._cells)
        return (yield from _as_step(self._query(q, cells)))


class DateMapSeries[W, V](DateSeriesBase[V]):
    """Map resolved query answers while preserving a date-keyed surface.

    ``keys()`` aliases the source domain. ``fn`` receives the source's resolved
    answer at each query, including any miss sentinel returned by its query.
    """

    def __init__(
        self,
        name: str,
        source: BaseSeries[date, date, W],
        fn: Callable[[W], V],
    ) -> None:
        super().__init__(name)
        self._source = source
        self._fn = fn

    def keys(self) -> RuleBase[Iterable[date]]:
        return self._source.keys()

    def compute(self, q: date, /) -> Step[V]:
        w = yield from get_at(self._source, q)
        return self._fn(w)


class DateMap2Series[W1, W2, V](DateSeriesBase[V]):
    """Combine two date-keyed series' resolved answers at the same query.

    ``merge_keys`` constructs only the advertised domain; it does not affect
    query computation. It defaults to the unique sorted ``date_union``.
    """

    def __init__(
        self,
        name: str,
        left: BaseSeries[date, date, W1],
        right: BaseSeries[date, date, W2],
        fn: Callable[[W1, W2], V],
        *,
        merge_keys: Callable[[tuple[Iterable[date], ...]], Iterable[date]] | None = None,
    ) -> None:
        super().__init__(name)
        self._left = left
        self._right = right
        self._fn = fn
        self._keys: RuleBase[Iterable[date]] = _MapNKeys(
            name,
            (left, right),
            date_union if merge_keys is None else merge_keys,
        )

    def keys(self) -> RuleBase[Iterable[date]]:
        return self._keys

    def compute(self, q: date, /) -> Step[V]:
        a = yield from get_at(self._left, q)
        b = yield from get_at(self._right, q)
        return self._fn(a, b)


class DateExtendSeries[W](DateSeriesBase[W]):
    """Answer from ``base`` until the continuation's own domain begins.

    ``continuation`` receives the last base ``date`` and owns queries at or
    after its first key. Point queries are dispatched wholly to one side:
    dates before the first continuation key — including the gap after the
    last base date — use the base, so an as-of (``last``) base query carries
    forward across the seam; later dates use the continuation. Queries at or
    before the last base date never materialize the continuation. The base
    domain must be finite.
    """

    def __init__(
        self,
        name: str,
        base: DateSeriesBase[W],
        continuation: Callable[[date], DateSeriesBase[W]],
    ) -> None:
        super().__init__(name)
        self._base = base
        self._continuation = _ContinueFrom(name, base, continuation)
        self._keys = _ContinueKeys(name, base, self._continuation)

    @classmethod
    def define[W2](
        cls,
        name: str,
        base: DateSeriesBase[W2],
    ) -> Callable[[Callable[[date], DateSeriesBase[W2]]], DateExtendSeries[W2]]:
        """Decorator: build a ``DateExtendSeries`` from a continuation factory."""

        def decorator(
            continuation: Callable[[date], DateSeriesBase[W2]],
        ) -> DateExtendSeries[W2]:
            return DateExtendSeries(name, base, continuation)

        return decorator

    def keys(self) -> RuleBase[Iterable[date]]:
        return self._keys

    def compute(self, q: date, /) -> Step[W]:
        last: date | None = None
        for k in (yield from get(self._base.keys())):
            if not k < q:
                return (yield from get_at(self._base, q))
            last = k
        if last is None:
            raise ValueError(f"{self.name}: base series is empty")
        cont = yield from get(self._continuation)
        first = next(iter((yield from get(cont.keys()))), None)
        if first is None or q < first:
            return (yield from get_at(self._base, q))
        return (yield from get_at(cont, q))
