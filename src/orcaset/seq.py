# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from dataclasses import dataclass

from .f import F


@dataclass(frozen=True, slots=True)
class Cons[T]:
    """Lazy cons cell. ``tail`` is an ``F[Seq[T]]`` so forcing it through a
    Context reuses the eval cache: the same continuation object is returned
    on every force of the same tail node.
    """

    head: T
    tail: F[Seq[T]]


class Empty[T]:
    pass


type Seq[T] = Cons[T] | Empty[T]


def empty[T]() -> Seq[T]:
    return Empty()
