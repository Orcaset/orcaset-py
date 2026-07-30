# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Generator, Hashable
from dataclasses import dataclass
from typing import Any, cast

from orcaset.rule import _UNIT, Node, Rule, Step

type RuleKey = tuple[int, Hashable]
type Target = Rule[Any, Any] | Node[Any]


_MISSING: Any = object()


class CycleError(RuntimeError):
    """Raised when a demand cycle is detected."""

    def __init__(self, path: tuple[RuleKey, ...], *, names: dict[int, str] | None = None) -> None:
        self.path = path
        names = names or {}
        parts = " -> ".join(
            _format_cell(names.get(cell[0], str(cell[0])), cell[1]) for cell in path
        )
        super().__init__(f"Demand cycle: {parts}")


@dataclass(frozen=True, slots=True)
class DepNode:
    """A node in a demand dependency tree."""

    name: str
    key: Hashable
    value: Any
    deps: tuple[DepNode, ...] = ()

    def __str__(self) -> str:
        return self.format()

    def format(self, *, indent: str = "  ") -> str:
        """Render this node and its dependencies as an indented tree."""
        return "\n".join(self._lines(indent, 0))

    def _lines(self, indent: str, depth: int) -> list[str]:
        prefix = indent * depth
        lines = [f"{prefix}{_format_cell(self.name, self.key)} = {self.value!r}"]
        for dep in self.deps:
            lines.extend(dep._lines(indent, depth + 1))
        return lines


def _format_cell(name: str, key: Hashable) -> str:
    if key is _UNIT:
        return name
    return f"{name}@{key!r}"


def _completed(value: Any) -> Step[Any]:
    """A step that immediately completes with `value`."""
    return value
    yield  # unreachable; makes this function a generator


class Context:
    def __init__(self):
        self._compute_cache: dict[RuleKey, Any] = {}
        self._deps: dict[RuleKey, set[RuleKey]] = {}
        self._stack: list[RuleKey] = []
        self._on_stack: set[RuleKey] = set()
        self._targets: dict[int, Target] = {}

    def demand[K: Hashable, V](self, rule: Rule[K, V], key: K) -> V:
        return self._resolve(rule, key, lambda: rule.compute(key))

    def ask[V](self, node: Node[V]) -> V:
        return self._resolve(node, _UNIT, lambda: node.compute())

    def dependencies[K: Hashable, V](self, rule: Rule[K, V], key: K) -> DepNode:
        """Demand ``rule``/``key``, then return its dependency tree."""
        self.demand(rule, key)
        return self._dep_node((rule.id, key), seen=set())

    def node_dependencies[V](self, node: Node[V]) -> DepNode:
        """Ask ``node``, then return its dependency tree."""
        self.ask(node)
        return self._dep_node((node.id, _UNIT), seen=set())

    def _resolve[V](
        self,
        target: Target,
        key: Hashable,
        compute: Callable[[], Step[V] | V],
    ) -> V:
        cell: RuleKey = (target.id, key)
        self._targets[target.id] = target

        if cell in self._on_stack:
            self._raise_cycle(cell)

        cached = self._compute_cache.get(cell, _MISSING)
        if cached is not _MISSING:
            return cast(V, cached)

        # Suspending scheduler: each frame is a paused ``compute`` generator.
        # Yielded ``Demand``s either resolve from cache immediately or push a
        # new frame; finished frames send their return value back into the
        # frame that demanded them. Every ``compute`` body runs exactly once
        # per cell and no Python recursion is used.
        stack_start = len(self._stack)
        frames: list[Step[Any]] = []
        self._push(cell, compute(), frames)
        to_send: Any = None
        try:
            while frames:
                try:
                    demanded = frames[-1].send(to_send)
                except StopIteration as stop:
                    finished = self._stack.pop()
                    self._on_stack.discard(finished)
                    frames.pop()
                    self._compute_cache[finished] = stop.value
                    to_send = stop.value
                else:
                    dep_target = demanded.target
                    child: RuleKey = (dep_target.id, demanded.key)
                    self._targets[dep_target.id] = dep_target
                    self._record_dep(self._stack[-1], child)

                    dep_cached = self._compute_cache.get(child, _MISSING)
                    if dep_cached is not _MISSING:
                        to_send = dep_cached
                    elif child in self._on_stack:
                        self._raise_cycle(child)
                    else:
                        self._push(child, _start(dep_target, demanded.key), frames)
                        to_send = None
        finally:
            for frame in reversed(frames):
                frame.close()
            for stale in self._stack[stack_start:]:
                self._on_stack.discard(stale)
            del self._stack[stack_start:]

        return cast(V, self._compute_cache[cell])

    def _push(self, cell: RuleKey, result: Step[Any] | Any, frames: list[Step[Any]]) -> None:
        self._stack.append(cell)
        self._on_stack.add(cell)
        if isinstance(result, Generator):
            frames.append(result)
        else:
            frames.append(_completed(result))

    def _raise_cycle(self, cell: RuleKey) -> None:
        cycle_start = self._stack.index(cell)
        path = tuple(self._stack[cycle_start:])
        raise CycleError(path, names=self._target_names())

    def _dep_node(self, cell: RuleKey, *, seen: set[RuleKey]) -> DepNode:
        target_id, key = cell
        name = self._targets[target_id].name
        value = self._compute_cache[cell]
        if cell in seen:
            return DepNode(name=name, key=key, value=value, deps=())

        seen = seen | {cell}
        children = sorted(
            self._deps.get(cell, ()),
            key=lambda c: (self._targets[c[0]].name, repr(c[1]), c[0]),
        )
        return DepNode(
            name=name,
            key=key,
            value=value,
            deps=tuple(self._dep_node(child, seen=seen) for child in children),
        )

    def _target_names(self) -> dict[int, str]:
        return {k: v.name for k, v in self._targets.items()}

    def _record_dep(self, consumer: RuleKey, dependency: RuleKey) -> None:
        self._deps.setdefault(consumer, set()).add(dependency)


def _start(target: Target, key: Hashable) -> Step[Any] | Any:
    if isinstance(target, Node):
        return target.compute()
    return target.compute(key)
