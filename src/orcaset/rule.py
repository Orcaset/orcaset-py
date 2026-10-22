# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Hashable, Mapping
from dataclasses import dataclass
from typing import Any, cast, overload

from orcaset.ids import next_id
from orcaset.maybe import Maybe, isna

_UNIT: Hashable = object()
_NO_SEED_DISTANCE: Any = object()


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


class AutoName(str):
    """A rule name derived by the library because none was given.

    Behaves as a plain ``str``; the type only marks that the name was not
    chosen by the user, e.g. so statements can insist on explicit names.
    """


def auto_name(kind: str) -> AutoName:
    """A fresh ``kind#n`` name for a rule that has nothing better to show."""
    return AutoName(f"{kind}#{next_id()}")


def derived_name(op: str, *operands: _Identity | str) -> AutoName:
    """Name a combinator result after its operation and operands.

    Explicitly named operands appear by name. Operands with derived names of
    the form ``op(...)`` collapse to ``op(…)`` so nesting stays short. Only
    stored names are read; no rule is evaluated.
    """
    return AutoName(f"{op}({', '.join(_operand_label(operand) for operand in operands)})")


def _operand_label(operand: _Identity | str) -> str:
    if isinstance(operand, str):
        return operand
    name = operand.name
    if isinstance(name, AutoName) and "(" in name:
        return f"{name[: name.index('(')]}(…)"
    return name


class _Identity:
    """Shared id/name for ``Rule`` and ``KeyedRule``.

    ``name`` is optional. Without one, ``default_name`` supplies a derived
    name the first time it is read. Reading a name never evaluates a rule.
    """

    def __init__(self, name: str | None = None, *, structural: bool = False) -> None:
        self._name = name
        self._id = next_id()
        self._structural = structural

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        if self._name is None:
            self._name = AutoName(self.default_name())
        return self._name

    @property
    def named(self) -> bool:
        """Whether this target was given an explicit name."""
        return self._name is not None and not isinstance(self._name, AutoName)

    def default_name(self) -> str:
        """The name used when none was given.

        Override to derive a more descriptive name. Implementations must only
        read construction-time data (types, functions, other rules' names),
        never evaluate rules.
        """
        return f"{type(self).__name__}#{self._id}"

    @property
    def structural(self) -> bool:
        """Whether this target is internal traversal machinery."""
        return self._structural


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


type Effect[V] = Generator[Demand[Any], Any, V]
"""A suspendable computation that yields ``Demand``s and returns a ``V``."""


@overload
def get_at[K: Hashable, V](rule: KeyedRule[K, V], key: K) -> Effect[V]: ...


@overload
def get_at[K: Hashable, V](
    rule: KeyedRule[K, V],
    key: K,
    *,
    seed: V,
    distance: Callable[[V, V], float],
    tol: float | None = None,
    max_iter: int | None = None,
) -> Effect[V]: ...


def get_at[K: Hashable, V](
    rule: KeyedRule[K, V],
    key: K,
    *,
    seed: V | Any = _NO_SEED_DISTANCE,
    distance: Callable[[V, V], float] | Any = _NO_SEED_DISTANCE,
    tol: float | None = None,
    max_iter: int | None = None,
) -> Effect[V]:
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
def get[V](rule: Rule[V]) -> Effect[V]: ...


@overload
def get[V](
    rule: Rule[V],
    *,
    seed: V,
    distance: Callable[[V, V], float],
    tol: float | None = None,
    max_iter: int | None = None,
) -> Effect[V]: ...


def get[V](
    rule: Rule[V],
    *,
    seed: V | Any = _NO_SEED_DISTANCE,
    distance: Callable[[V, V], float] | Any = _NO_SEED_DISTANCE,
    tol: float | None = None,
    max_iter: int | None = None,
) -> Effect[V]:
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
    if seed is _NO_SEED_DISTANCE and distance is _NO_SEED_DISTANCE:
        return None
    if seed is _NO_SEED_DISTANCE or distance is _NO_SEED_DISTANCE:
        raise TypeError("seed and distance must be provided together")
    return Iterate(seed=seed, distance=distance, tol=tol, max_iter=max_iter)


class Rule[V](_Identity, ABC):
    """A single memoized computation (no key)."""

    @abstractmethod
    def compute(self) -> Effect[V] | V:
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
    """A keyed family of memoized computations."""

    @abstractmethod
    def compute(self, key: K, /) -> Effect[V] | V:
        """Compute the value of this rule at ``key``.

        Same generator conventions as ``Rule.compute``, but keyed. The
        parameter is positional-only so overrides may rename it for their key
        space (e.g. ``q`` for query-keyed rules).
        """
        ...


_VAL_NAME_WIDTH = 24


def _fn_name(fn: Callable[..., Any]) -> str | None:
    name = getattr(fn, "__name__", None)
    return name if isinstance(name, str) and name.isidentifier() else None


class Fn[V](Rule[V]):
    """Unkeyed rule whose ``compute`` delegates to a zero-arg function.

    Use to lift a zero-arg function to a rule, which may yield demands for other rules.
    Without a ``name``, the function's ``__name__`` is used (``Fn#n`` for lambdas).
    """

    def __init__(
        self,
        fn: Callable[[], Effect[V] | V],
        *,
        name: str | None = None,
        structural: bool = False,
    ) -> None:
        super().__init__(name, structural=structural)
        self._fn = fn

    def compute(self) -> Effect[V] | V:
        return self._fn()

    def default_name(self) -> str:
        return _fn_name(self._fn) or super().default_name()

    @classmethod
    @overload
    def define[V2](cls, fn: Callable[[], Effect[V2] | V2], /) -> Fn[V2]: ...
    @classmethod
    @overload
    def define[V2](
        cls, *, name: str | None = None
    ) -> Callable[[Callable[[], Effect[V2] | V2]], Fn[V2]]: ...
    @classmethod
    def define[V2](
        cls,
        fn: Callable[[], Effect[V2] | V2] | None = None,
        /,
        *,
        name: str | None = None,
    ) -> Fn[V2] | Callable[[Callable[[], Effect[V2] | V2]], Fn[V2]]:
        """Decorator: build an ``Fn`` from a zero-arg compute function.

        The decorated function becomes the rule. Use bare (``@Fn.define``) to
        name the rule after the function, or ``@Fn.define(name=...)``.
        """

        def decorator(fn: Callable[[], Effect[V2] | V2]) -> Fn[V2]:
            return cls(fn, name=name)

        return decorator if fn is None else decorator(fn)


class KeyedFn[K: Hashable, V](KeyedRule[K, V]):
    """Keyed rule whose ``compute`` delegates to a one-arg function.

    Use to lift a one-arg function to a keyed rule, which may yield demands for other rules.
    Without a ``name``, the function's ``__name__`` is used (``KeyedFn#n`` for lambdas).
    """

    def __init__(self, fn: Callable[[K], Effect[V] | V], *, name: str | None = None) -> None:
        super().__init__(name)
        self._fn = fn

    def compute(self, key: K, /) -> Effect[V] | V:
        return self._fn(key)

    def default_name(self) -> str:
        return _fn_name(self._fn) or super().default_name()

    @classmethod
    @overload
    def define[K2: Hashable, V2](
        cls, fn: Callable[[K2], Effect[V2] | V2], /
    ) -> KeyedFn[K2, V2]: ...
    @classmethod
    @overload
    def define[K2: Hashable, V2](
        cls, *, name: str | None = None
    ) -> Callable[[Callable[[K2], Effect[V2] | V2]], KeyedFn[K2, V2]]: ...
    @classmethod
    def define[K2: Hashable, V2](
        cls,
        fn: Callable[[K2], Effect[V2] | V2] | None = None,
        /,
        *,
        name: str | None = None,
    ) -> KeyedFn[K2, V2] | Callable[[Callable[[K2], Effect[V2] | V2]], KeyedFn[K2, V2]]:
        """Decorator: build a ``KeyedFn`` from a keyed compute function.

        The decorated function becomes the rule. Use bare (``@KeyedFn.define``)
        to name the rule after the function, or ``@KeyedFn.define(name=...)``.
        """

        def decorator(fn: Callable[[K2], Effect[V2] | V2]) -> KeyedFn[K2, V2]:
            return cls(fn, name=name)

        return decorator if fn is None else decorator(fn)


class Val[V](Rule[V]):
    """Unkeyed rule holding a plain value.

    Use to lift a plain value to a rule. Without a ``name``, a short ``repr``
    of the value is used.
    """

    def __init__(self, value: V, *, name: str | None = None) -> None:
        super().__init__(name)
        self.value = value

    def compute(self) -> Effect[V]:
        return self.value  # type: ignore[return-value]

    def default_name(self) -> str:
        text = repr(self.value)
        if len(text) > _VAL_NAME_WIDTH:
            text = f"{text[: _VAL_NAME_WIDTH - 1]}…"
        return text


class KeyedVal[K: Hashable, V](KeyedRule[K, V]):
    """Keyed rule backed by a ``Mapping`` of plain values.

    Use to lift a ``Mapping`` of plain values to a keyed rule. A missing key raises ``KeyError``.
    """

    def __init__(self, values: Mapping[K, V], *, name: str | None = None) -> None:
        super().__init__(name)
        self.values = values

    def compute(self, key: K, /) -> Effect[V]:
        return self.values[key]  # type: ignore[return-value]
