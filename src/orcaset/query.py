# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Common ``QueryFn`` helpers for series."""

from __future__ import annotations

from orcaset.maybe import Maybe, Na
from orcaset.rule import Rule, Step, get
from orcaset.series import Cells, Key


def exact[K: Key, V](q: K, cells: Cells[K, V]) -> Step[Maybe[V]]:
    """Return the cell exactly at ``q``, or ``Na`` if it is absent."""
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            node = yield from get(node.tail)
        elif q < node.key:
            return Na
        elif node.key == q:
            return (yield from get(node.cell))
        else:
            node = yield from get(node.tail)
    return Na


def last[K: Key, V](q: K, cells: Cells[K, V]) -> Step[Maybe[V]]:
    """Return the latest strictly prior or exactly matching cell, or ``Na``."""
    pending: Rule[V] | None = None
    node = yield from get(cells)
    while node is not None:
        if node.key < q:
            pending = node.cell
            node = yield from get(node.tail)
        elif node.key == q:
            return (yield from get(node.cell))
        elif q < node.key:
            break
        else:
            node = yield from get(node.tail)
    if pending is None:
        return Na
    return (yield from get(pending))
