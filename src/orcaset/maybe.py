# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Absent answers.

A series cell exists only where data exists, so absence in a stream is
positional: a key with no cell simply has no cell. Queries, by contrast, are
total — any query may be asked of any series — so :meth:`~orcaset.series.Series.query`
answers ``Maybe[V]``: either a value or :data:`MISSING`.

``Missing`` is a dedicated sentinel rather than ``None`` so that ``None``
stays available as an ordinary modelled value, and so a function that falls
off the end cannot silently fabricate an absent answer.

Every place an answer is consumed — a mapped view, a pointwise combination, a
recursive cell, a resampled grid — must state a policy for absence. The
combinators here name the three: :func:`strict` (absence is an error),
:func:`propagate` (absence spreads), and :func:`fill` (absence is a known
neutral value).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from .f import F, Pure


class MissingError(LookupError):
    """Raised where an absent answer is not an acceptable input."""


class Missing:
    """The absent answer.

    A singleton: use :data:`MISSING`. Test with ``isinstance(x, Missing)``,
    which narrows ``Maybe[V]`` to ``V`` on the negative branch. ``Missing`` is
    deliberately not falsy — ``if answer:`` would conflate it with ``0.0``.
    """

    __slots__: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final[Missing] = Missing()
"""The absent answer."""

type Maybe[V] = V | Missing
"""An answer that may be absent. ``V`` must not itself contain ``Missing``."""

MISSING_NODE: Final[F[Missing]] = Pure(MISSING, label="MISSING")
"""The shared absent-answer node.

Reduces and views should return this rather than minting ``Pure(MISSING)``
per query, so unanswerable questions cost one cache entry per context.
"""


# Consuming an answer -------------------------------------------------------


def unwrap[V](answer: Maybe[V], *, what: str = "answer") -> V:
    """Return the value, raising :class:`MissingError` if it is absent."""
    if isinstance(answer, Missing):
        raise MissingError(f"{what} is missing")
    return answer


def or_else[V](answer: Maybe[V], default: V) -> V:
    """Return the value, or ``default`` if it is absent."""
    return default if isinstance(answer, Missing) else answer


# Combining answers ---------------------------------------------------------


def strict[A, B, W](
    op: Callable[[A, B], W], *, what: str = "combine"
) -> Callable[[Maybe[A], Maybe[B]], Maybe[W]]:
    """Absence is an error: raise :class:`MissingError` if either side is absent.

    The default policy for combinations that have no meaningful answer over
    partial coverage (ratios, differences against a required base).
    """

    def combine(a: Maybe[A], b: Maybe[B]) -> Maybe[W]:
        if isinstance(a, Missing) or isinstance(b, Missing):
            raise MissingError(f"{what}: operand missing ({a!r}, {b!r})")
        return op(a, b)

    return combine


def propagate[A, B, W](op: Callable[[A, B], W]) -> Callable[[Maybe[A], Maybe[B]], Maybe[W]]:
    """Absence spreads: the result is absent if either side is absent."""

    def combine(a: Maybe[A], b: Maybe[B]) -> Maybe[W]:
        if isinstance(a, Missing) or isinstance(b, Missing):
            return MISSING
        return op(a, b)

    return combine


def fill[V](zero: V, op: Callable[[V, V], V]) -> Callable[[Maybe[V], Maybe[V]], Maybe[V]]:
    """Absence is ``zero``: substitute it on either side, then combine.

    Correct exactly when ``zero`` is an identity for ``op`` — ``0.0`` with
    addition, ``1.0`` with multiplication. Outer-merging cohorts that cover
    disjoint spans is the canonical use. Fill silently turns a coverage bug
    into a plausible number, so prefer :func:`strict` unless the identity is
    genuinely meaningful.
    """

    def combine(a: Maybe[V], b: Maybe[V]) -> Maybe[V]:
        return op(zero if isinstance(a, Missing) else a, zero if isinstance(b, Missing) else b)

    return combine
