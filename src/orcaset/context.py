# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .f import Bind, Delay, F, Map, Pure


@dataclass(frozen=True, slots=True)
class _Eval:
    node: F[Any]


@dataclass(frozen=True, slots=True)
class _MapK:
    f: Callable[[Any], Any]
    node: F[Any]


@dataclass(frozen=True, slots=True)
class _BindK:
    f: Callable[[Any], F[Any]]
    node: F[Any]


@dataclass(frozen=True, slots=True)
class _Join:
    node: F[Any]


@dataclass(frozen=True, slots=True)
class _Done:
    node: F[Any]


@dataclass(frozen=True, slots=True)
class _Mark:
    """Sentinel so nested ``run`` stops when its subtree has produced a value."""


type _Frame = _Eval | _MapK | _BindK | _Join | _Done | _Mark


@dataclass(slots=True)
class Context:
    """Iterative Free interpreter with id-keyed result cache.

    Cache keys are ``F.id`` values, not object identity, so shared subgraphs
    and re-forced sequence tails reuse the same computed results.
    """

    stack: list[F[Any]] = field(default_factory=list)
    frames: list[_Frame] = field(default_factory=list)
    values: list[Any] = field(default_factory=list)
    edges: set[tuple[F[Any], F[Any]]] = field(default_factory=set)
    cache: dict[int, Any] = field(default_factory=dict)

    def run[A](self, node: F[A]) -> A:
        mark = _Mark()
        self.frames.append(mark)
        self.frames.append(_Eval(node))
        while self.frames[-1] is not mark:
            self._step()
        self.frames.pop()
        return self.values.pop()

    def _step(self) -> None:
        frame = self.frames.pop()
        match frame:
            case _Eval(node):
                self._eval(node)
            case _MapK(f, node):
                v = self.values.pop()
                self.values.append(f(v))
                self.frames.append(_Done(node))
            case _BindK(f, node):
                v = self.values.pop()
                fb = f(v)
                self.frames.append(_Join(node))
                self.frames.append(_Eval(fb))
            case _Join(node):
                self.frames.append(_Done(node))
            case _Done(node):
                self.cache[node.id] = self.values[-1]
                self.stack.pop()
            case _Mark():
                raise RuntimeError("internal error: mark frame reached _step")
            case _:
                raise TypeError(f"unknown frame: {frame!r}")

    def _eval(self, node: F[Any]) -> None:
        if self.stack:
            self.edges.add((self.stack[-1], node))

        if node.id in self.cache:
            self.values.append(self.cache[node.id])
            return

        if any(frame.id == node.id for frame in self.stack):
            raise RuntimeError(f"cycle detected: {node!r}")

        self.stack.append(node)
        match node:
            case Pure(value=v):
                self.values.append(v)
                self.frames.append(_Done(node))
            case Delay(thunk=t):
                self.values.append(t())
                self.frames.append(_Done(node))
            case Map(source=src, f=f):
                self.frames.append(_MapK(f, node))
                self.frames.append(_Eval(src))
            case Bind(source=src, f=f):
                self.frames.append(_BindK(f, node))
                self.frames.append(_Eval(src))
            case _:
                raise TypeError(f"unknown F node: {type(node).__name__}")


def _fmt(node: F[Any]) -> str:
    name = node.label if node.label is not None else repr(node)
    return f"({node.id}) {name}"


def _fmt_node(ctx: Context, node: F[Any]) -> str:
    label = _fmt(node)
    if node.id in ctx.cache:
        return f"{label} = {ctx.cache[node.id]!r}"
    return label


def _children_of(ctx: Context, parent: F[Any]) -> list[F[Any]]:
    seen: set[int] = set()
    children: list[F[Any]] = []
    for p, child in ctx.edges:
        if p.id == parent.id and child.id not in seen:
            seen.add(child.id)
            children.append(child)
    return children


def _render(
    ctx: Context,
    node: F[Any],
    *,
    prefix: str,
    is_last: bool,
    is_root: bool,
    seen: set[int],
) -> None:
    if is_root:
        print(_fmt_node(ctx, node))
    else:
        branch = "└─ " if is_last else "├─ "
        print(f"{prefix}{branch}{_fmt_node(ctx, node)}")

    if node.id in seen:
        return
    seen.add(node.id)

    kids = _children_of(ctx, node)
    child_prefix = "" if is_root else prefix + ("   " if is_last else "│  ")
    for i, kid in enumerate(kids):
        _render(
            ctx,
            kid,
            prefix=child_prefix,
            is_last=i == len(kids) - 1,
            is_root=False,
            seen=seen,
        )


def print_deps(ctx: Context, root: F[Any]) -> None:
    """Print the dependency tree for ``root``.

    Runs ``root`` if it is not already cached; does not re-run when present.
    """
    if root.id not in ctx.cache:
        ctx.run(root)
    _render(ctx, root, prefix="", is_last=True, is_root=True, seen=set())


def print_edges(ctx: Context) -> None:
    for parent, child in sorted(ctx.edges, key=lambda e: (_fmt(e[0]), _fmt(e[1]))):
        print("--------------------------------")
        print(f"{_fmt(child)} -> {_fmt(parent)}")
