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
