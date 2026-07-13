# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .f import F


@dataclass(slots=True)
class Context:
    """Evaluation engine with id-keyed result cache.

    Cache keys are ``F.id`` values, not object identity, so shared subgraphs
    and re-forced sequence tails reuse the same computed results.
    """

    stack: list[F[Any]] = field(default_factory=list)
    edges: set[tuple[F[Any], F[Any]]] = field(default_factory=set)
    cache: dict[int, Any] = field(default_factory=dict)

    def run[A](self, node: F[A]) -> A:
        if self.stack:
            self.edges.add((self.stack[-1], node))

        if node.id in self.cache:
            return self.cache[node.id]

        if any(frame.id == node.id for frame in self.stack):
            raise RuntimeError(f"cycle detected: {node!r}")

        self.stack.append(node)
        try:
            result = node.eval(self)
            self.cache[node.id] = result
            return result
        finally:
            self.stack.pop()


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
