# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator, Hashable
from typing import Any, cast

from orcaset.ids import next_id


class Demand[K: Hashable, V]:
    """A request for another cell's value, yielded from `Rule.compute`.

    Yielding a `Demand` suspends the current computation until the requested
    cell has been resolved; the resolved value is sent back into the generator
    as the result of the `yield` expression. Prefer the typed `fetch` helper
    (`value = yield from fetch(rule, key)`) over yielding `Demand` directly.
    """

    __slots__ = ("key", "rule")

    def __init__(self, rule: Rule[K, V], key: K) -> None:
        self.rule = rule
        self.key = key


type Step[V] = Generator[Demand[Any, Any], Any, V]
"""A suspendable computation that yields `Demand`s and returns a `V`."""


def fetch[K: Hashable, V](rule: Rule[K, V], key: K) -> Step[V]:
    """Request the value of `rule` at `key` from within `Rule.compute`.

    Use with `yield from` so the resolved value keeps its type:

        prev = yield from fetch(self, prior_key)
    """
    value = yield Demand(rule, key)
    return cast(V, value)


class Rule[K: Hashable, V](ABC):
    def __init__(self, name: str):
        self._name = name
        self._id = next_id()

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def compute(self, key: K, /) -> Step[V] | V:
        """Compute the value of this rule at `key`.

        Rules with dependencies are written as generators: request other cells
        with `value = yield from fetch(rule, key)` and `return` the result.
        Each body runs exactly once per cell; execution suspends at `fetch`
        while dependencies resolve. Leaf rules may return a plain value.

        The parameter is positional-only so overrides may rename it for their
        key space (e.g. `q` for query-keyed rules).

        Note: a plain return value must not itself be a generator, since a
        returned generator is treated as a suspendable computation. Wrap
        generator-valued data in a replayable container instead.
        """
        ...
