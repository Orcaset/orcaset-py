# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Arithmetic combinators over series."""

from __future__ import annotations

import math
from collections.abc import Callable, Generator, Sequence
from typing import Any

from orcaset import maybe
from orcaset.maybe import Maybe, Na
from orcaset.query import filled
from orcaset.rule import Effect, Rule, derived_name, get, get_at
from orcaset.series import (
    Chain,
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


def map[K: Key, W, T](
    source: Series[K, Any, W],
    *,
    fn: Callable[[W], Effect[T] | T],
    name: str | None = None,
) -> Series[K, T, T]:
    """Map ``fn`` over the query answers of ``source``.

    The result keeps the source's spine keys. Every query — on or off the
    spine — queries ``source`` at the same key and maps its answer, so cells
    and queries both honor the source's own query semantics.

    ``fn`` may return a plain value or an effect that demands other rules.
    Returned generators are interpreted as computations, not data.
    """
    name = name if name is not None else derived_name("map", source)

    def value_at(key: K) -> Effect[T]:
        value = yield from get_at(source, key)
        return (yield from _as_effect(fn(value)))

    def query(q: K, _cells: Chain[K, T]) -> Effect[T]:
        return (yield from value_at(q))

    def step(cells: Chain[K, Any]) -> Effect[tuple[K, Thunk[T], Chain[K, Any]] | None]:
        node = yield from get(cells)
        if node is None:
            return None
        return node.key, Thunk(lambda key=node.key: value_at(key)), node.tail

    return Series(unfold_cells(seed=source._cells, step=step, name=name), query, name=name)


def map2[K: Key, L, R, T](
    left: Series[K, Any, L],
    right: Series[K, Any, R],
    *,
    fn: Callable[[L, R], Effect[T] | T],
    merge_keys: KeyMerge[K],
    name: str | None = None,
) -> Series[K, T, T]:
    """Map ``fn`` over two series' query answers across their merged domain.

    ``fn`` may return a plain value or an effect that demands other rules.
    Returned generators are interpreted as computations, not data.
    """
    name = name if name is not None else derived_name("map2", left, right)

    def value_at(key: K) -> Effect[T]:
        left_value = yield from get_at(left, key)
        right_value = yield from get_at(right, key)
        return (yield from _as_effect(fn(left_value, right_value)))

    def query(q: K, _cells: Chain[K, T]) -> Effect[T]:
        return (yield from value_at(q))

    def cell(key: K) -> Thunk[T]:
        return Thunk(lambda: value_at(key))

    cells = merge_cells([left._cells, right._cells], merge_keys, cell, name=name)
    return Series(cells, query, name=name)


def mapn[K: Key, W, T](
    sources: Sequence[Series[K, Any, W]],
    *,
    fn: Callable[[Sequence[W]], Effect[T] | T],
    merge_keys: KeyMerge[K],
    name: str | None = None,
) -> Series[K, T, T]:
    """Map ``fn`` over ``sources``' query answers across their merged domain.

    Every query — on or off the spine — queries all sources at the same key,
    including sources whose head did not contribute it and sources past their
    own domain. The answers are passed unchanged and in source order to ``fn``.
    The function decides how to combine them (see ``query.filled`` for the
    arithmetic ops' missing-value policy).

    ``fn`` may return a plain value or an effect that demands other rules.
    Returned generators are interpreted as computations, not data.
    """
    if not sources:
        raise ValueError("mapn requires at least one source series")
    sources = tuple(sources)
    name = name if name is not None else derived_name("mapn", *sources)

    def values_at(key: K) -> Effect[T]:
        values: list[W] = []
        for source in sources:
            values.append((yield from get_at(source, key)))
        return (yield from _as_effect(fn(values)))

    def query(q: K, _cells: Chain[K, T]) -> Effect[T]:
        return (yield from values_at(q))

    def cell(key: K) -> Thunk[T]:
        return Thunk(lambda: values_at(key))

    chains = [source._cells for source in sources]
    return Series(merge_cells(chains, merge_keys, cell, name=name), query, name=name)


def add[K: Key](
    *sources: Series[K, Any, Maybe[float]],
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
    name: str | None = None,
) -> Series[K, Maybe[float], Maybe[float]]:
    """Sum of ``sources`` over their merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    name = name if name is not None else derived_name("add", *sources)
    return mapn(sources, fn=filled(sum, fill), merge_keys=merge_keys, name=name)


def mul[K: Key](
    *sources: Series[K, Any, Maybe[float]],
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
    name: str | None = None,
) -> Series[K, Maybe[float], Maybe[float]]:
    """Product of ``sources`` over their merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    name = name if name is not None else derived_name("mul", *sources)
    return mapn(sources, fn=filled(math.prod, fill), merge_keys=merge_keys, name=name)


def neg[K: Key](
    source: Series[K, Any, Maybe[float]],
    /,
    *,
    name: str | None = None,
) -> Series[K, Maybe[float], Maybe[float]]:
    """``-source`` over the source's own domain. ``Na`` propagates."""
    name = name if name is not None else derived_name("neg", source)
    return map(source, fn=maybe.map_some(lambda value: -value), name=name)


def scale[K: Key](
    source: Series[K, Any, Maybe[float]],
    factor: float | Rule[float],
    /,
    *,
    name: str | None = None,
) -> Series[K, Maybe[float], Maybe[float]]:
    """``source * factor`` over the source's own domain. ``Na`` propagates."""
    if name is None:
        name = derived_name("scale", source, factor if isinstance(factor, Rule) else repr(factor))

    if not isinstance(factor, Rule):
        return map(source, fn=maybe.map_some(lambda value: value * factor), name=name)

    def apply(value: Maybe[float]) -> Effect[Maybe[float]]:
        return maybe.mul_some(value, (yield from get(factor)))

    return map(source, fn=apply, name=name)


def sub[K: Key](
    left: Series[K, Any, Maybe[float]],
    right: Series[K, Any, Maybe[float]],
    /,
    *,
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
    name: str | None = None,
) -> Series[K, Maybe[float], Maybe[float]]:
    """``left - right`` over the merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    difference = filled(lambda values: values[0] - values[1], fill)
    return map2(
        left,
        right,
        fn=lambda left_value, right_value: difference((left_value, right_value)),
        merge_keys=merge_keys,
        name=name if name is not None else derived_name("sub", left, right),
    )


def div[K: Key](
    left: Series[K, Any, Maybe[float]],
    right: Series[K, Any, Maybe[float]],
    /,
    *,
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
    name: str | None = None,
) -> Series[K, Maybe[float], Maybe[float]]:
    """``left / right`` over the merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    quotient = filled(lambda values: values[0] / values[1], fill)
    return map2(
        left,
        right,
        fn=lambda left_value, right_value: quotient((left_value, right_value)),
        merge_keys=merge_keys,
        name=name if name is not None else derived_name("div", left, right),
    )
