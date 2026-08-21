# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Hashable
from dataclasses import dataclass
from typing import Any, cast, overload

from orcaset.ids import next_id
from orcaset.maybe import Maybe, isna

# Sentinel cache key for unkeyed ``Cell`` demands. Not a valid user key space.
_UNIT: Hashable = object()

# Distinguishes "seed/distance omitted" from a legitimate ``seed=None``.
_MISSING: Any = object()


@dataclass(frozen=True, slots=True)
class Iterate[V]:
    """Fixed-point policy for a cyclic ``get`` / ``get_at``.

    ``seed`` is the initial guess for the demanded value. ``distance`` measures
    successive guesses of the same type. Registering a spec on any demand in a
    cycle is enough: the context uses that target as a cut from any query
    entrypoint, and iterates until every seeded cell in the cycle satisfies
    ``distance(prev, next) < tol`` (or the context default).
    """

    seed: V
    distance: Callable[[V, V], float]
    tol: float | None = None
    max_iter: int | None = None


def abs_distance(a: float, b: float) -> float:
    """Absolute distance on ``float`` values."""
    return abs(a - b)


def maybe_abs_distance(a: Maybe[float], b: Maybe[float]) -> float:
    """Absolute distance on ``Maybe[float]``; ``Na`` vs non-``Na`` is infinite."""
    if isna(a) or isna(b):
        return 0.0 if isna(a) and isna(b) else float("inf")
    return abs(a - b)


class _Identity:
    """Shared id/name for ``Rule`` and ``KeyedRule``."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._id = next_id()

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name


class Demand[V]:
    """A request for another computation's value, yielded from ``compute``.

    Yielding a ``Demand`` suspends the current computation until the requested
    value has been resolved; the resolved value is sent back into the generator
    as the result of the ``yield`` expression. Prefer ``get`` / ``get_at`` over
    yielding ``Demand`` directly.

    ``iterate`` registers a cut on ``target`` at ``key``. When a demand cycle
    includes that cell, the scheduler injects ``iterate.seed`` and re-runs the
    component until every seeded cell is close under its ``distance``.
    """

    __slots__ = ("iterate", "key", "target")

    def __init__(
        self,
        target: KeyedRule[Any, V] | Rule[V],
        key: Hashable,
        iterate: Iterate[V] | None = None,
    ) -> None:
        self.target = target
        self.key = key
        self.iterate = iterate


type Step[V] = Generator[Demand[Any], Any, V]
"""A suspendable computation that yields ``Demand``s and returns a ``V``."""


@overload
def get_at[K: Hashable, V](rule: KeyedRule[K, V], key: K) -> Step[V]: ...


@overload
def get_at[K: Hashable, V](
    rule: KeyedRule[K, V],
    key: K,
    *,
    seed: V,
    distance: Callable[[V, V], float],
    tol: float | None = None,
    max_iter: int | None = None,
) -> Step[V]: ...


def get_at[K: Hashable, V](
    rule: KeyedRule[K, V],
    key: K,
    *,
    seed: V | Any = _MISSING,
    distance: Callable[[V, V], float] | Any = _MISSING,
    tol: float | None = None,
    max_iter: int | None = None,
) -> Step[V]:
    """Request the value of ``rule`` at ``key`` from within ``compute``.

    Use with ``yield from`` so the resolved value keeps its type:

        prev = yield from get_at(self, prior_key)

    To solve a demand cycle, pass ``seed`` and ``distance`` together. Both are
    typed against this call's return type ``V``: ``seed`` is an initial guess
    for the fetched value, and ``distance`` maps two ``V``s to a residual.
    One spec anywhere in the cycle is enough, from any query entrypoint; they
    are ignored when the demand is not part of a cycle.
    """
    value = yield Demand(rule, key, _iterate(seed, distance, tol, max_iter))
    return cast(V, value)


@overload
def get[V](rule: Rule[V]) -> Step[V]: ...


@overload
def get[V](
    rule: Rule[V],
    *,
    seed: V,
    distance: Callable[[V, V], float],
    tol: float | None = None,
    max_iter: int | None = None,
) -> Step[V]: ...


def get[V](
    rule: Rule[V],
    *,
    seed: V | Any = _MISSING,
    distance: Callable[[V, V], float] | Any = _MISSING,
    tol: float | None = None,
    max_iter: int | None = None,
) -> Step[V]:
    """Request the value of an unkeyed ``Rule`` from within ``compute``.

    Use with ``yield from``:

        cells = yield from get(self._cells)

    ``seed`` and ``distance`` have the same cyclic-solve meaning as in
    ``get_at``, and are typed against this call's return type ``V``.
    One spec anywhere in the cycle is enough, from any query entrypoint.
    """
    value = yield Demand(rule, _UNIT, _iterate(seed, distance, tol, max_iter))
    return cast(V, value)


def _iterate[V](
    seed: V | Any,
    distance: Callable[[V, V], float] | Any,
    tol: float | None,
    max_iter: int | None,
) -> Iterate[V] | None:
    if seed is _MISSING and distance is _MISSING:
        return None
    if seed is _MISSING or distance is _MISSING:
        raise TypeError("seed and distance must be provided together")
    return Iterate(seed=seed, distance=distance, tol=tol, max_iter=max_iter)


class Rule[V](_Identity, ABC):
    """A single memoized computation (no key).

    Subclass to override ``compute``. For a one-off body, use ``Cell`` or
    ``@Cell.define`` instead.
    """

    @abstractmethod
    def compute(self) -> Step[V] | V:
        """Compute this rule's value.

        Rules with dependencies are written as generators: request other
        computations with ``value = yield from get(rule)`` or
        ``get_at(keyed, key)`` and ``return`` the result. Acyclic bodies run
        exactly once; cyclic ``get``/``get_at`` calls that pass ``seed`` and
        ``distance`` re-run the component until every seeded cell is close.
        Leaf rules may return a plain value.

        Note: a plain return value must not itself be a generator, since a
        returned generator is treated as a suspendable computation. Wrap
        generator-valued data in a replayable container instead.
        """
        ...


class KeyedRule[K: Hashable, V](_Identity, ABC):
    """A keyed family of memoized computations.

    Subclass to override ``compute`` (as ``PeriodSeries`` does). For a one-off
    body, use ``KeyedCell`` or ``@KeyedCell.define`` instead.
    """

    @abstractmethod
    def compute(self, key: K, /) -> Step[V] | V:
        """Compute the value of this rule at ``key``.

        Same generator conventions as ``Rule.compute``, but keyed. The
        parameter is positional-only so overrides may rename it for their key
        space (e.g. ``q`` for query-keyed rules).
        """
        ...


class Cell[V](Rule[V]):
    """Unkeyed rule whose ``compute`` delegates to a zero-arg ``fn``.

    ``fn`` is public and may be replaced; a new ``Context`` is required for a
    later ``get`` to see the change. Subclass ``Rule`` when ``compute``
    needs extra state or methods.
    """

    def __init__(self, name: str, fn: Callable[[], Step[V] | V]) -> None:
        super().__init__(name)
        self.fn = fn

    def compute(self) -> Step[V] | V:
        return self.fn()

    @classmethod
    def define[V2](cls, name: str) -> Callable[[Callable[[], Step[V2] | V2]], Cell[V2]]:
        """Decorator: build a ``Cell`` from a zero-arg compute function.

        The decorated function becomes the cell, so its body can close over
        that name — including ``get`` of itself for a demand cycle.
        """

        def decorator(fn: Callable[[], Step[V2] | V2]) -> Cell[V2]:
            return cls(name, fn)

        return decorator


class KeyedCell[K: Hashable, V](KeyedRule[K, V]):
    """Keyed rule whose ``compute`` delegates to a one-arg ``fn``.

    ``fn`` is public and may be replaced; a new ``Context`` is required for a
    later ``get_at`` to see the change. Subclass ``KeyedRule`` when
    ``compute`` needs extra state or methods.
    """

    def __init__(self, name: str, fn: Callable[[K], Step[V] | V]) -> None:
        super().__init__(name)
        self.fn = fn

    def compute(self, key: K, /) -> Step[V] | V:
        return self.fn(key)

    @classmethod
    def define[K2: Hashable, V2](
        cls,
        name: str,
    ) -> Callable[[Callable[[K2], Step[V2] | V2]], KeyedCell[K2, V2]]:
        """Decorator: build a ``KeyedCell`` from a keyed compute function.

        The decorated function becomes the cell, so its body can close over
        that name.
        """

        def decorator(fn: Callable[[K2], Step[V2] | V2]) -> KeyedCell[K2, V2]:
            return cls(name, fn)

        return decorator
