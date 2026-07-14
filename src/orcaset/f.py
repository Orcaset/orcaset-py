# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import count
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import Context

_ids = count()


def _new_id() -> int:
    return next(_ids)


@dataclass(frozen=True, slots=True, eq=False)
class F[A]:
    """Lazy monadic expression: an inert Free-style AST evaluated by Context.run.

    Equality and hashing are by ``id`` only so deep Map/Bind chains do not
    recurse when recorded in ``Context.edges``.
    """

    label: str | None = field(default=None, kw_only=True)
    id: int = field(default_factory=_new_id, kw_only=True)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, F) and self.id == other.id

    def __hash__(self) -> int:
        return self.id

    @staticmethod
    def pure[T](value: T, *, label: str | None = None) -> F[T]:
        return Pure(value, label=label)

    @staticmethod
    def delay[T](thunk: Callable[[], T], *, label: str | None = None) -> F[T]:
        """Defer a computation until first force; result is cached by id in Context."""
        return Delay(thunk, label=label)

    def map[B](self, f: Callable[[A], B], *, label: str | None = None) -> F[B]:
        return Map(self, f, label=label)

    def apply[B, C](self: F[Callable[[B], C]], fa: F[B], *, label: str | None = None) -> F[C]:
        return self.bind(lambda f: fa.map(f), label=label)

    def bind[B](self, f: Callable[[A], F[B]], *, label: str | None = None) -> F[B]:
        return Bind(self, f, label=label)

    def run(self, ctx: Context) -> A:
        return ctx.run(self)


@dataclass(frozen=True, slots=True, eq=False)
class Pure[A](F[A]):
    value: A

    def __repr__(self) -> str:
        return f"Pure({self.value!r})"


@dataclass(frozen=True, slots=True, eq=False)
class Delay[A](F[A]):
    thunk: Callable[[], A]

    def __repr__(self) -> str:
        return f"Delay({self.thunk!r})"


@dataclass(frozen=True, slots=True, eq=False)
class Map[A, B](F[B]):
    source: F[A]
    f: Callable[[A], B]

    def __repr__(self) -> str:
        return f"Map({self.source!r}, {self.f!r})"


@dataclass(frozen=True, slots=True, eq=False)
class Bind[A, B](F[B]):
    source: F[A]
    f: Callable[[A], F[B]]

    def __repr__(self) -> str:
        return f"Bind({self.source!r}, {self.f!r})"
