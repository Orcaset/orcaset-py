# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from typing import Any, cast

from orcaset.rule import Rule

type RuleKey = tuple[int, Hashable]


_MISSING: Any = object()


class _PendingDemand(BaseException):
    def __init__(self, rule: Rule[Any, Any], key: Hashable):
        self.rule = rule
        self.key = key


class CycleError(RuntimeError):
    """Raised when a non-circular demand cycle is detected."""

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


class _Fetch[K: Hashable, V]:
    def __init__(self, context: Context):
        self._context = context

    def __call__(self, rule: Rule[K, V], key: K) -> V:
        child = (rule.id, key)
        self._context._rules[rule.id] = rule
        if self._context._stack:
            self._context._record_dep(self._context._stack[-1], child)

        cached = self._context._compute_cache.get(child, _MISSING)
        if cached is not _MISSING:
            return cast(V, cached)

        if child in self._context._stack:
            cycle_start = self._context._stack.index(child)
            path = tuple(self._context._stack[cycle_start:])
            raise CycleError(path, names=self._context._rule_names())

        raise _PendingDemand(rule, key)


class Context:
    def __init__(self):
        self._compute_cache: dict[RuleKey, Any] = {}
        self._deps: dict[RuleKey, set[RuleKey]] = {}
        self._stack: list[RuleKey] = []
        self._rules: dict[int, Rule[Any, Any]] = {}

    def demand[K: Hashable, V](self, rule: Rule[K, V], key: K) -> V:
        cell = (rule.id, key)
        self._rules[rule.id] = rule

        # Check for circular dependencies and raise an error if found
        if cell in self._stack:
            cycle_start = self._stack.index(cell)
            path = tuple(self._stack[cycle_start:])
            raise CycleError(path, names=self._rule_names())

        # Return cached value if available
        cached = self._compute_cache.get(cell, _MISSING)
        if cached is not _MISSING:
            return cast(V, cached)

        # Otherwise compute and cache values using an explicit dependency stack
        # TODO: Revise so that it doesn't restart computation by popping by raising an exception to pop from
        # _Fetch.__call__ back to this while loop
        # TODO: Consider using a marker object to detect the start of the stack instead of len()
        stack_start = len(self._stack)
        self._stack.append(cell)
        try:
            while len(self._stack) > stack_start:
                current = self._stack[-1]
                current_rule = self._rules[current[0]]
                try:
                    value = current_rule.compute(_Fetch(self), current[1])
                except _PendingDemand as pending:
                    self._stack.append((pending.rule.id, pending.key))
                else:
                    self._compute_cache[current] = value
                    self._stack.pop()
        finally:
            del self._stack[stack_start:]

        return cast(V, self._compute_cache[cell])

    def dependencies[K: Hashable, V](self, rule: Rule[K, V], key: K) -> DepNode:
        """Demand `rule`/`key`, then return its dependency tree."""
        self.demand(rule, key)
        return self._dep_node((rule.id, key), seen=set())

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
