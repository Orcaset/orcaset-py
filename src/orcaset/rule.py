# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator, Hashable
from typing import Any, cast

from orcaset.ids import next_id

# Sentinel cache key for unkeyed ``Rule`` demands. Not a valid user key space.
_UNIT: Hashable = object()


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
    """

    __slots__ = ("key", "target")

    def __init__(self, target: KeyedRule[Any, V] | Rule[V], key: Hashable) -> None:
        self.target = target
        self.key = key


type Step[V] = Generator[Demand[Any], Any, V]
"""A suspendable computation that yields ``Demand``s and returns a ``V``."""


def get_at[K: Hashable, V](rule: KeyedRule[K, V], key: K) -> Step[V]:
    """Request the value of ``rule`` at ``key`` from within ``compute``.

    Use with ``yield from`` so the resolved value keeps its type:

        prev = yield from get_at(self, prior_key)
    """
    value = yield Demand(rule, key)
    return cast(V, value)


def get[V](rule: Rule[V]) -> Step[V]:
    """Request the value of an unkeyed ``Rule`` from within ``compute``.

    Use with ``yield from``:

        cells = yield from get(self._cells)
    """
    value = yield Demand(rule, _UNIT)
    return cast(V, value)


class Rule[V](_Identity, ABC):
    """A single memoized computation (no key)."""

    @abstractmethod
    def compute(self) -> Step[V] | V:
        """Compute this rule's value.

        Rules with dependencies are written as generators: request other
        computations with ``value = yield from get(rule)`` or
        ``get_at(keyed, key)`` and ``return`` the result. Each body runs exactly
        once; execution suspends at ``get``/``get_at`` while dependencies
        resolve. Leaf rules may return a plain value.

        Note: a plain return value must not itself be a generator, since a
        returned generator is treated as a suspendable computation. Wrap
        generator-valued data in a replayable container instead.
        """
        ...


class KeyedRule[K: Hashable, V](_Identity, ABC):
    """A keyed family of memoized computations."""

    @abstractmethod
    def compute(self, key: K, /) -> Step[V] | V:
        """Compute the value of this rule at ``key``.

        Same generator conventions as ``Rule.compute``, but keyed. The parameter
        is positional-only so overrides may rename it for their key space
        (e.g. ``q`` for query-keyed rules).
        """
        ...
