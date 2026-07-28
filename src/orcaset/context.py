# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Generator, Hashable
from dataclasses import dataclass
from typing import Any, cast

from orcaset.rule import Rule, Step

type RuleKey = tuple[int, Hashable]


_MISSING: Any = object()


class CycleError(RuntimeError):
    """Raised when a demand cycle is detected."""

    def __init__(self, path: tuple[RuleKey, ...], *, names: dict[int, str] | None = None) -> None:
        self.path = path
        names = names or {}
        parts = " -> ".join(f"{names.get(cell[0], cell[0])}@{cell[1]!r}" for cell in path)
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
        lines = [f"{prefix}{self.name}@{self.key!r} = {self.value!r}"]
        for dep in self.deps:
            lines.extend(dep._lines(indent, depth + 1))
        return lines


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
        self._rules: dict[int, Rule[Any, Any]] = {}

    def demand[K: Hashable, V](self, rule: Rule[K, V], key: K) -> V:
        cell: RuleKey = (rule.id, key)
        self._rules[rule.id] = rule

        # Check for circular dependencies and raise an error if found
        if cell in self._on_stack:
            self._raise_cycle(cell)

        # Return cached value if available
        cached = self._compute_cache.get(cell, _MISSING)
        if cached is not _MISSING:
            return cast(V, cached)

        # Otherwise run a suspending scheduler: each frame is a paused
        # `compute` generator. Yielded `Demand`s either resolve from cache
        # immediately or push a new frame; finished frames send their return
        # value back into the frame that demanded them. Every `compute` body
        # runs exactly once per cell and no Python recursion is used, so
        # arbitrarily deep dependency chains are safe.
        stack_start = len(self._stack)
        frames: list[Step[Any]] = []
        self._push(cell, rule.compute(key), frames)
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
                    dep_rule = demanded.rule
                    child: RuleKey = (dep_rule.id, demanded.key)
                    self._rules[dep_rule.id] = dep_rule
                    self._record_dep(self._stack[-1], child)

                    dep_cached = self._compute_cache.get(child, _MISSING)
                    if dep_cached is not _MISSING:
                        to_send = dep_cached
                    elif child in self._on_stack:
                        self._raise_cycle(child)
                    else:
                        self._push(child, dep_rule.compute(demanded.key), frames)
                        to_send = None
        finally:
            for frame in reversed(frames):
                frame.close()
            for stale in self._stack[stack_start:]:
                self._on_stack.discard(stale)
            del self._stack[stack_start:]

        return cast(V, self._compute_cache[cell])

    def dependencies[K: Hashable, V](self, rule: Rule[K, V], key: K) -> DepNode:
        """Demand `rule`/`key`, then return its dependency tree."""
        self.demand(rule, key)
        return self._dep_node((rule.id, key), seen=set())

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
        raise CycleError(path, names=self._rule_names())

    def _dep_node(self, cell: RuleKey, *, seen: set[RuleKey]) -> DepNode:
        rule_id, key = cell
        name = self._rules[rule_id].name
        value = self._compute_cache[cell]
        if cell in seen:
            return DepNode(name=name, key=key, value=value, deps=())

        seen = seen | {cell}
        children = sorted(
            self._deps.get(cell, ()),
            key=lambda c: (self._rules[c[0]].name, repr(c[1]), c[0]),
        )
        return DepNode(
            name=name,
            key=key,
            value=value,
            deps=tuple(self._dep_node(child, seen=seen) for child in children),
        )

    def _rule_names(self) -> dict[int, str]:
        return {k: v.name for k, v in self._rules.items()}

    def _record_dep(self, consumer: RuleKey, dependency: RuleKey) -> None:
        self._deps.setdefault(consumer, set()).add(dependency)
