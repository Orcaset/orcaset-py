# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import count

from .context import Context

_ids = count()


def _new_id() -> int:
    return next(_ids)


@dataclass(frozen=True, slots=True)
class F[A]:
    """Lazy monadic expression: transformations are values, evaluated by run()."""

    label: str | None = field(default=None, kw_only=True)
    id: int = field(default_factory=_new_id, kw_only=True)

    @staticmethod
    def pure[T](value: T, *, label: str | None = None) -> F[T]:
        return Pure(value, label=label)

    @staticmethod
    def delay[T](thunk: Callable[[], T], *, label: str | None = None) -> F[T]:
        """Defer a computation until first eval; result is cached by id in Context."""
        return Delay(thunk, label=label)

    def map[B](self, f: Callable[[A], B], *, label: str | None = None) -> F[B]:
        return Map(self, f, label=label)

    def apply[B, C](self: F[Callable[[B], C]], fa: F[B], *, label: str | None = None) -> F[C]:
        return Apply(self, fa, label=label)

    def bind[B](self, f: Callable[[A], F[B]], *, label: str | None = None) -> F[B]:
        return Bind(self, f, label=label)

    def run(self, ctx: Context) -> A:
        return ctx.run(self)

    def eval(self, ctx: Context) -> A:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Pure[A](F[A]):
    value: A

    def eval(self, ctx: Context) -> A:
        return self.value

    def __repr__(self) -> str:
        return f"Pure({self.value!r})"


@dataclass(frozen=True, slots=True)
class Delay[A](F[A]):
    thunk: Callable[[], A]

    def eval(self, ctx: Context) -> A:
        return self.thunk()

    def __repr__(self) -> str:
        return f"Delay({self.thunk!r})"


@dataclass(frozen=True, slots=True)
class Map[A, B](F[B]):
    source: F[A]
    f: Callable[[A], B]

    def eval(self, ctx: Context) -> B:
        return self.f(ctx.run(self.source))

    def __repr__(self) -> str:
        return f"Map({self.source!r}, {self.f!r})"


@dataclass(frozen=True, slots=True)
class Apply[A, B](F[B]):
    func: F[Callable[[A], B]]
    arg: F[A]

    def eval(self, ctx: Context) -> B:
        return ctx.run(self.func)(ctx.run(self.arg))

    def __repr__(self) -> str:
        return f"Apply({self.func!r}, {self.arg!r})"


@dataclass(frozen=True, slots=True)
class Bind[A, B](F[B]):
    source: F[A]
    f: Callable[[A], F[B]]

    def eval(self, ctx: Context) -> B:
        return ctx.run(self.f(ctx.run(self.source)))

    def __repr__(self) -> str:
        return f"Bind({self.source!r}, {self.f!r})"
