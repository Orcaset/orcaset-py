# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Generator, Hashable, Iterable
from dataclasses import dataclass
from typing import Protocol, Self

from orcaset.rule import Cell, KeyedRule, Rule, Step, get


class Key(Hashable, Protocol):
    """Series key: hashable (cell identity) and comparable (lazy scans).

    ``a < b`` means "a is entirely before b". The order need not be total:
    keys that overlap (e.g. overlapping ``Period``s) may be mutually
    incomparable. Scans only require that domain streams are strictly
    ascending, so anything entirely past a probe stays past it.
    """

    def __lt__(self, other: Self, /) -> bool: ...


class Thunk[V]:
    """Nominal wrapper for a deferred cell computation.

    In an unfold result, anything that is not a ``Thunk`` is a plain value,
    including callables and all other objects. Wrap deferred computation in
    ``Thunk`` explicitly. This makes the value slot unambiguous: there is no
    ``callable()`` sniffing.
    """

    __slots__ = ("fn",)

    def __init__(self, fn: Callable[[], Step[V] | V]) -> None:
        self.fn = fn


@dataclass(frozen=True, slots=True)
class Cons[K: Key, V]:
    """One materialized node of a series' cell chain.

    ``tail`` resolves to the next node or ``None`` (exhaustion). Tails are
    ordinary rules: memoized per context and free to demand other rules,
    enabling value-dependent domains.
    """

    key: K
    cell: Rule[V]
    tail: Rule[Cons[K, V] | None]


type Cells[K: Key, V] = Rule[Cons[K, V] | None]
type UnfoldFn[S, K: Key, V] = Callable[
    [S],
    Step[tuple[K, V | Thunk[V], S] | None] | tuple[K, V | Thunk[V], S] | None,
]
"""Produce a cell and next state from an unfold state, or end the chain."""

type QueryFn[Q, K: Key, V, W] = Callable[[Q, Cells[K, V]], Step[W] | W]
"""Fold a query over a cell chain, with optional early termination."""


class Series[Q: Hashable, K: Key, V, W](KeyedRule[Q, W]):
    """A queryable series backed by an effectful cons-list built by unfold."""

    def __init__(self, name: str, cells: Cells[K, V], query: QueryFn[Q, K, V, W]) -> None:
        super().__init__(name)
        self._cells = cells
        self._query = query

    @property
    def cells(self) -> Cells[K, V]:
        """The rule resolving the first node of this series."""
        return self._cells

    def compute(self, q: Q, /) -> Step[W]:
        return (yield from _as_step(self._query(q, self._cells)))

    @classmethod
    def unfold[S](
        cls,
        name: str,
        query: QueryFn[Q, K, V, W],
        *,
        seed: S,
        step: UnfoldFn[S, K, V],
    ) -> Series[Q, K, V, W]:
        """Build a series by repeatedly applying ``step`` to an evolving state."""
        return cls(name, _UnfoldRule(name, None, seed, step), query)

    @classmethod
    def of(
        cls,
        name: str,
        query: QueryFn[Q, K, V, W],
        pairs: Iterable[tuple[K, V | Thunk[V]]],
    ) -> Series[Q, K, V, W]:
        """Build a series from eagerly materialized literal pairs."""
        materialized = tuple(pairs)

        def step(index: int) -> tuple[K, V | Thunk[V], int] | None:
            if index == len(materialized):
                return None
            key, value = materialized[index]
            return key, value, index + 1

        return cls.unfold(name, query, seed=0, step=step)

    @classmethod
    def define[S](
        cls,
        name: str,
        query: QueryFn[Q, K, V, W],
        *,
        seed: S,
    ) -> Callable[[UnfoldFn[S, K, V]], Series[Q, K, V, W]]:
        """Decorator form of ``unfold`` for self-referential series bodies."""

        def decorator(step: UnfoldFn[S, K, V]) -> Series[Q, K, V, W]:
            return cls.unfold(name, query, seed=seed, step=step)

        return decorator


class _UnfoldRule[S, K: Key, V](Rule[Cons[K, V] | None]):
    """Rule that materializes one unfold node and its deferred tail."""

    def __init__(
        self,
        series_name: str,
        prev_key: K | None,
        state: S,
        step: UnfoldFn[S, K, V],
    ) -> None:
        name = (
            f"{series_name}.cells"
            if prev_key is None
            else f"{series_name}.tail@{prev_key}"
        )
        super().__init__(name)
        self._series_name = series_name
        self._prev_key = prev_key
        self._state = state
        self._step = step

    def compute(self) -> Step[Cons[K, V] | None]:
        result = yield from _as_step(self._step(self._state))
        if result is None:
            return None
        key, value, next_state = result
        if self._prev_key is not None and not self._prev_key < key:
            raise ValueError(
                f"keys must be strictly ascending: got {self._prev_key!r} then {key!r}"
            )
        return Cons(
            key,
            Cell(f"{self._series_name}@{key}", _cell_fn(value)),
            _UnfoldRule(self._series_name, key, next_state, self._step),
        )


def _cell_fn[V](value: V | Thunk[V]) -> Callable[[], Step[V] | V]:
    if isinstance(value, Thunk):
        return value.fn
    if isinstance(value, Generator):
        raise TypeError(
            "live generator as a cell value; wrap the computation in Thunk(lambda: ...)"
        )
    return lambda value=value: value


def _as_step[V](value: Step[V] | V) -> Step[V]:
    """Normalize plain and generator return values to a ``Step``."""
    if isinstance(value, Generator):
        return value

    def completed() -> Step[V]:
        if False:
            yield
        return value

    return completed()


def keys_until[K: Key, V](cells: Cells[K, V], stop: K) -> Step[list[K]]:
    """Collect keys through ``stop`` without forcing cells or a past frontier."""
    keys: list[K] = []
    node = yield from get(cells)
    while node is not None:
        if stop < node.key:
            break
        keys.append(node.key)
        node = yield from get(node.tail)
    return keys
