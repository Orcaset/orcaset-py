# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Arithmetic combinators over series with lazily merged domains.

A combined series answers every query ``q`` by querying each source at ``q``
and handing the answers — ``Na`` included — to ``fn``. Each source's own
``QueryFn`` therefore decides how sub-key and off-domain queries resolve; the
result never has to be told a query policy of its own. ``combine`` has no
opinion on ``Na``; that policy lives in ``fn``.

The arithmetic ops propagate ``Na`` by default. Passing ``fill`` substitutes
that value for every ``Na`` a source answers, before the arithmetic runs —
``add(..., fill=0.0)`` treats a series as zero wherever it has nothing to
say. ``Na`` does not distinguish "outside my domain" from "my query policy
has no answer here" (an ``exact`` monthly source queried at a half-month is
``Na``), so a filled combination silently drops such contributions; keep the
default where that distinction matters. With ``fill`` set, keys outside every
source's domain answer ``fn([fill, ...])`` rather than ``Na``.

The result's spine is the union of the source domains re-tiled by a
``KeyMerge`` (``period_union`` splits overlapping periods at every boundary;
``date_union`` dedupes). Spine cells are the same delegated computation at
the spine keys, so chain walks and direct queries cannot disagree, and the
chain is a valid ``extend`` continuation.

Nonlinear combinations (``mul``, ``div``) do not commute with aggregation:
``price * volume`` over a quarter is ``price(quarter) * volume(quarter)``, not
the sum of monthly products. When a source cannot answer the coarser query
its ``QueryFn`` typically returns ``Na``, which propagates. To aggregate the
spine instead, wrap the exposed chain with an explicit fold:
``Series(name, combined.cells, summing_query)``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from orcaset.maybe import Maybe, Na, isna
from orcaset.rule import Step, get_at
from orcaset.series import Cells, Key, KeyMerge, Series, Thunk, merge_cells

type _Source[K: Key] = Series[K, K, Any, Maybe[float]]
type _Combined[K: Key] = Series[K, K, Maybe[float], Maybe[float]]


def combine[K: Key](
    name: str,
    sources: Sequence[_Source[K]],
    *,
    fn: Callable[[Sequence[Maybe[float]]], Maybe[float]],
    merge_keys: KeyMerge[K],
) -> _Combined[K]:
    """Combine ``sources`` pointwise; the domain is their lazily merged union.

    Every query — on or off the spine — queries all sources at the same key,
    including sources whose head did not contribute it and sources past their
    own domain; each answers per its own ``QueryFn``. The answers, in source
    order and with any ``Na`` left in place, are passed to ``fn``, which
    decides how misses combine (see ``filled`` for the arithmetic ops'
    policy).
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


def filled(
    fn: Callable[[Sequence[float]], float],
    fill: Maybe[float] = Na,
) -> Callable[[Sequence[Maybe[float]]], Maybe[float]]:
    """Lift a float fold to ``Maybe`` answers with a fill policy.

    Each ``Na`` is replaced by ``fill`` before ``fn`` runs; when ``fill`` is
    itself ``Na`` (the default) any ``Na`` makes the result ``Na``. This is the
    ``fn`` the arithmetic ops pass to ``combine``.
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

    ``Na`` propagates unless ``fill`` is given; ``fill=0.0`` sums whatever is
    present.
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

    ``Na`` propagates unless ``fill`` is given; ``fill=1.0`` is the identity,
    ``fill=0.0`` zeroes the product wherever a factor is missing.
    """
    return combine(name, sources, fn=filled(math.prod, fill), merge_keys=merge_keys)


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

    ``Na`` propagates unless ``fill`` is given; ``fill`` applies to both sides.
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

    ``Na`` propagates unless ``fill`` is given; ``fill`` applies to both
    sides. A zero denominator raises ``ZeroDivisionError``: zeros are bugs to
    surface, not missing data — including a missing denominator under
    ``fill=0.0``.
    """
    return combine(
        name,
        (left, right),
        fn=filled(lambda values: values[0] / values[1], fill),
        merge_keys=merge_keys,
    )
