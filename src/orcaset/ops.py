# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Arithmetic combinators over series."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from orcaset.maybe import Maybe, Na, isna, map_some
from orcaset.rule import Step, get, get_at
from orcaset.series import Cells, Key, KeyMerge, Series, Thunk, merge_cells, unfold_cells

type _Source[K: Key] = Series[K, Any, Maybe[float]]
type _Combined[K: Key] = Series[K, Maybe[float], Maybe[float]]


def combine[K: Key](
    name: str,
    sources: Sequence[_Source[K]],
    *,
    fn: Callable[[Sequence[Maybe[float]]], Maybe[float]],
    merge_keys: KeyMerge[K],
) -> _Combined[K]:
    """Combine ``sources`` pointwise where the domain is the lazily merged union
    of source domains.

    Every query — on or off the spine — queries all sources at the same key,
    including sources whose head did not contribute it and sources past their
    own domain. The answers, in source order and with any ``Na`` left in place,
    are passed to ``fn``, which decides how misses combine (see ``filled`` for
    the arithmetic ops' policy).
    """
    if not sources:
        raise ValueError("combine requires at least one source series")
    sources = tuple(sources)

    def values_at(key: K) -> Step[Maybe[float]]:
        values: list[Maybe[float]] = []
        for source in sources:
            values.append((yield from get_at(source, key)))
        return fn(values)

    def query(q: K, _cells: Cells[K, Maybe[float]]) -> Step[Maybe[float]]:
        return (yield from values_at(q))

    def cell(key: K) -> Thunk[Maybe[float]]:
        return Thunk(lambda: values_at(key))

    chains = [source.cells for source in sources]
    return Series(name, merge_cells(name, chains, merge_keys, cell), query)


def map_values[K: Key, W, T](
    name: str,
    source: Series[K, Any, W],
    *,
    fn: Callable[[W], T],
) -> Series[K, T, T]:
    """Map ``fn`` over the query answers of ``source``.

    The result keeps the source's spine keys. Every query — on or off the
    spine — queries ``source`` at the same key and maps its answer, so cells
    and queries both honor the source's own query semantics.
    """

    def value_at(key: K) -> Step[T]:
        value = yield from get_at(source, key)
        return fn(value)

    def query(q: K, _cells: Cells[K, T]) -> Step[T]:
        return (yield from value_at(q))

    def step(cells: Cells[K, Any]) -> Step[tuple[K, Thunk[T], Cells[K, Any]] | None]:
        node = yield from get(cells)
        if node is None:
            return None
        return node.key, Thunk(lambda key=node.key: value_at(key)), node.tail

    return Series(name, unfold_cells(name, seed=source.cells, step=step), query)


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
    *sources: _Source[K],
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
) -> _Combined[K]:
    """Sum of ``sources`` over their merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    return combine(name, sources, fn=filled(sum, fill), merge_keys=merge_keys)


def mul[K: Key](
    name: str,
    /,
    *sources: _Source[K],
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
) -> _Combined[K]:
    """Product of ``sources`` over their merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    return combine(name, sources, fn=filled(math.prod, fill), merge_keys=merge_keys)


def neg[K: Key](
    name: str,
    source: _Source[K],
    /,
) -> _Combined[K]:
    """``-source`` over the source's own domain. ``Na`` propagates."""
    return map_values(name, source, fn=map_some(lambda value: -value))


def add_scalar[K: Key](
    name: str,
    source: _Source[K],
    scalar: float,
    /,
) -> _Combined[K]:
    """``source + scalar`` over the source's own domain. ``Na`` propagates."""
    return map_values(name, source, fn=map_some(lambda value: value + scalar))


def sub_scalar[K: Key](
    name: str,
    source: _Source[K],
    scalar: float,
    /,
) -> _Combined[K]:
    """``source - scalar`` over the source's own domain. ``Na`` propagates."""
    return map_values(name, source, fn=map_some(lambda value: value - scalar))


def mul_scalar[K: Key](
    name: str,
    source: _Source[K],
    scalar: float,
    /,
) -> _Combined[K]:
    """``source * scalar`` over the source's own domain. ``Na`` propagates."""
    return map_values(name, source, fn=map_some(lambda value: value * scalar))


def div_scalar[K: Key](
    name: str,
    source: _Source[K],
    scalar: float,
    /,
) -> _Combined[K]:
    """``source / scalar`` over the source's own domain. ``Na`` propagates."""
    return map_values(name, source, fn=map_some(lambda value: value / scalar))


def sub[K: Key](
    name: str,
    left: _Source[K],
    right: _Source[K],
    /,
    *,
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
) -> _Combined[K]:
    """``left - right`` over the merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    return combine(
        name,
        (left, right),
        fn=filled(lambda values: values[0] - values[1], fill),
        merge_keys=merge_keys,
    )


def div[K: Key](
    name: str,
    left: _Source[K],
    right: _Source[K],
    /,
    *,
    merge_keys: KeyMerge[K],
    fill: Maybe[float] = Na,
) -> _Combined[K]:
    """``left / right`` over the merged domain.

    ``Na`` propagates unless ``fill`` is a non-``Na`` value.
    """
    return combine(
        name,
        (left, right),
        fn=filled(lambda values: values[0] / values[1], fill),
        merge_keys=merge_keys,
    )
