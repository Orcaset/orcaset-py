# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Arithmetic combinators over series."""

from __future__ import annotations

import math
from collections.abc import Callable, Generator, Sequence
from typing import Any

from orcaset import maybe
from orcaset.maybe import Maybe, Na, isna
from orcaset.rule import Effect, Rule, get, get_at
from orcaset.series import (
    Cells,
    Key,
    KeyMerge,
    Series,
    Thunk,
    merge_cells,
    unfold_cells,
)


def _as_effect[V](value: Effect[V] | V) -> Effect[V]:
    """Resolve either an effectful or plain callback result."""
    if isinstance(value, Generator):
        return (yield from value)
    return value


def combine[K: Key, W, T](
    name: str,
    sources: Sequence[Series[K, Any, W]],
    *,
    fn: Callable[[Sequence[W]], Effect[T] | T],
    merge_keys: KeyMerge[K],
) -> Series[K, T, T]:
    """Combine ``sources`` pointwise where the domain is the lazily merged union
    of source domains.

    Every query — on or off the spine — queries all sources at the same key,
    including sources whose head did not contribute it and sources past their
    own domain. The answers are passed unchanged and in source order to ``fn``.
    The function decides how to combine them (see ``filled`` for the arithmetic
    ops' missing-value policy).

    ``fn`` may return a plain value or an effect that demands other rules.
    Returned generators are interpreted as computations, not data.
    """
    if not sources:
        raise ValueError("combine requires at least one source series")
    sources = tuple(sources)

    def values_at(key: K) -> Effect[T]:
        values: list[W] = []
        for source in sources:
            values.append((yield from get_at(source, key)))
        return (yield from _as_effect(fn(values)))

    def query(q: K, _cells: Cells[K, T]) -> Effect[T]:
        return (yield from values_at(q))

    def cell(key: K) -> Thunk[T]:
        return Thunk(lambda: values_at(key))

    chains = [source.cells for source in sources]
    return Series(name, merge_cells(name, chains, merge_keys, cell), query)


def map_values[K: Key, W, T](
    name: str,
    source: Series[K, Any, W],
    *,
    fn: Callable[[W], Effect[T] | T],
) -> Series[K, T, T]:
    """Map ``fn`` over the query answers of ``source``.

    The result keeps the source's spine keys. Every query — on or off the
    spine — queries ``source`` at the same key and maps its answer, so cells
    and queries both honor the source's own query semantics.

    ``fn`` may return a plain value or an effect that demands other rules.
    Returned generators are interpreted as computations, not data.
    """

    def value_at(key: K) -> Effect[T]:
        value = yield from get_at(source, key)
        return (yield from _as_effect(fn(value)))

    def query(q: K, _cells: Cells[K, T]) -> Effect[T]:
        return (yield from value_at(q))

    def step(cells: Cells[K, Any]) -> Effect[tuple[K, Thunk[T], Cells[K, Any]] | None]:
        node = yield from get(cells)
        if node is None:
            return None
        return node.key, Thunk(lambda key=node.key: value_at(key)), node.tail

    return Series(name, unfold_cells(name, seed=source.cells, step=step), query)


def map2[K: Key, L, R, T](
    name: str,
    left: Series[K, Any, L],
    right: Series[K, Any, R],
    *,
    fn: Callable[[L, R], Effect[T] | T],
    merge_keys: KeyMerge[K],
) -> Series[K, T, T]:
    """Map ``fn`` over two series' query answers across their merged domain.

    ``fn`` may return a plain value or an effect that demands other rules.
    Returned generators are interpreted as computations, not data.
    """

    def value_at(key: K) -> Effect[T]:
        left_value = yield from get_at(left, key)
        right_value = yield from get_at(right, key)
        return (yield from _as_effect(fn(left_value, right_value)))

    def query(q: K, _cells: Cells[K, T]) -> Effect[T]:
        return (yield from value_at(q))

    def cell(key: K) -> Thunk[T]:
        return Thunk(lambda: value_at(key))

    cells = merge_cells(name, [left.cells, right.cells], merge_keys, cell)
    return Series(name, cells, query)


def filled(
    fn: Callable[[Sequence[float]], float],
    fill: Maybe[float] = Na,
) -> Callable[[Sequence[Maybe[float]]], Maybe[float]]:
    """Lift a float fold to ``Maybe`` answers with a fill policy.

    Each ``Na`` is replaced by ``fill`` before ``fn`` runs; when ``fill`` is
    itself ``Na`` (the default) any ``Na`` makes the result ``Na``.
    """

    def apply(values: Sequence[Maybe[float]]) -> Maybe[float]:
        present: list[float] = []
        for value in values:
            if isna(value):
                if isna(fill):
                    return Na
                value = fill
            present.append(value)
        return fn(present)

    return apply


def add[K: Key](
    name: str,
    /,
    *sources: Series[K, Any, Maybe[float]],
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
) -> Series[K, Maybe[float], Maybe[float]]:
    """Sum of ``sources`` over their merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    return combine(name, sources, fn=filled(sum, fill), merge_keys=merge_keys)


def mul[K: Key](
    name: str,
    /,
    *sources: Series[K, Any, Maybe[float]],
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
) -> Series[K, Maybe[float], Maybe[float]]:
    """Product of ``sources`` over their merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    return combine(name, sources, fn=filled(math.prod, fill), merge_keys=merge_keys)


def neg[K: Key](
    name: str,
    source: Series[K, Any, Maybe[float]],
    /,
) -> Series[K, Maybe[float], Maybe[float]]:
    """``-source`` over the source's own domain. ``Na`` propagates."""
    return map_values(name, source, fn=maybe.map_some(lambda value: -value))


def scale[K: Key](
    name: str,
    source: Series[K, Any, Maybe[float]],
    factor: float | Rule[float],
    /,
) -> Series[K, Maybe[float], Maybe[float]]:
    """``source * factor`` over the source's own domain. ``Na`` propagates."""

    if not isinstance(factor, Rule):
        return map_values(name, source, fn=maybe.map_some(lambda value: value * factor))

    def apply(value: Maybe[float]) -> Effect[Maybe[float]]:
        return maybe.mul_some(value, (yield from get(factor)))

    return map_values(name, source, fn=apply)


def sub[K: Key](
    name: str,
    left: Series[K, Any, Maybe[float]],
    right: Series[K, Any, Maybe[float]],
    /,
    *,
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
) -> Series[K, Maybe[float], Maybe[float]]:
    """``left - right`` over the merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    difference = filled(lambda values: values[0] - values[1], fill)
    return map2(
        name,
        left,
        right,
        fn=lambda left_value, right_value: difference((left_value, right_value)),
        merge_keys=merge_keys,
    )


def div[K: Key](
    name: str,
    left: Series[K, Any, Maybe[float]],
    right: Series[K, Any, Maybe[float]],
    /,
    *,
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
) -> Series[K, Maybe[float], Maybe[float]]:
    """``left / right`` over the merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    quotient = filled(lambda values: values[0] / values[1], fill)
    return map2(
        name,
        left,
        right,
        fn=lambda left_value, right_value: quotient((left_value, right_value)),
        merge_keys=merge_keys,
    )
