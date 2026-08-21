# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from collections.abc import Callable
from typing import ClassVar, TypeIs, final


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


def some[V](value: V) -> Maybe[V]:
    """Return a value as a ``Maybe``."""
    return value


def value_or[V](value: Maybe[V], default: V) -> V:
    """Return `value` if not `Na`, otherwise `default`."""
    match value:
        case _NaType():
            return default
        case _:
            return value


def map_some[A, B](fn: Callable[[A], B]) -> Callable[[Maybe[A]], Maybe[B]]:
    """Lift ``fn`` over ``Maybe``: ``Na`` stays ``Na``."""

    def apply(a: Maybe[A]) -> Maybe[B]:
        return Na if isna(a) else fn(a)

    return apply


def map2_some[A, B, C](
    fn: Callable[[A, B], C],
) -> Callable[[Maybe[A], Maybe[B]], Maybe[C]]:
    """Lift ``fn`` over two ``Maybe``s: ``Na`` if either side is ``Na``."""

    def apply(a: Maybe[A], b: Maybe[B]) -> Maybe[C]:
        return Na if isna(a) or isna(b) else fn(a, b)

    return apply


def combine_some[V](
    values: tuple[Maybe[V] | V, ...],
    combine: Callable[[V, V], V],
) -> Maybe[V]:
    """Fold nonempty values with ``combine``, propagating ``Na``.

    An empty tuple has no value to seed the fold and therefore also returns
    ``Na``.
    """
    iterator = iter(values)
    first = next(iterator, Na)
    if isna(first):
        return Na

    result = first
    for value in iterator:
        if isna(value):
            return Na
        result = combine(result, value)
    return result


def add_some(values: tuple[Maybe[float], ...]) -> Maybe[float]:
    """Add float values, propagating ``Na``; an empty tuple returns ``Na``."""
    return combine_some(values, _add_floats)


def multiply_some(values: tuple[Maybe[float], ...]) -> Maybe[float]:
    """Multiply float values, propagating ``Na``; an empty tuple returns ``Na``."""
    return combine_some(values, _multiply_floats)


def _add_floats(left: float, right: float) -> float:
    return left + right


def _multiply_floats(left: float, right: float) -> float:
    return left * right
