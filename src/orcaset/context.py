# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Generator, Hashable
from dataclasses import dataclass, field
from typing import Any, NoReturn, cast

from orcaset.rule import _UNIT, Iterate, KeyedRule, Rule, Step

type RuleKey = tuple[int, Hashable]
type Target = KeyedRule[Any, Any] | Rule[Any]


_MISSING: Any = object()


class CycleError(RuntimeError):
    """Raised when a demand cycle is detected and no iterate policy was given."""

    def __init__(self, path: tuple[RuleKey, ...], *, names: dict[int, str] | None = None) -> None:
        self.path = path
        names = names or {}
        parts = " -> ".join(
            _format_cell(names.get(cell[0], str(cell[0])), cell[1]) for cell in path
        )
        super().__init__(f"Demand cycle: {parts}")


class ConvergenceError(RuntimeError):
    """Raised when a cyclic demand does not converge within ``max_iter``.

    ``values`` is the cut cell's seed followed by each computed iterate.
    ``residuals[i]`` is ``distance(values[i], values[i + 1])``. Inspect them
    to see oscillation, blow-up, or a slow crawl.
    """

    def __init__(
        self,
        cell: RuleKey,
        *,
        iterations: int,
        residual: float,
        tol: float,
        values: tuple[Any, ...],
        residuals: tuple[float, ...],
        names: dict[int, str] | None = None,
    ) -> None:
        self.cell = cell
        self.iterations = iterations
        self.residual = residual
        self.tol = tol
        self.values = values
        self.residuals = residuals
        names = names or {}
        label = _format_cell(names.get(cell[0], str(cell[0])), cell[1])
        lines = [
            (
                f"Failed to converge {label} after {iterations} iterations "
                f"(distance={residual}, tol={tol})"
            ),
            *_history_lines(values, residuals),
        ]
        super().__init__("\n".join(lines))


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


_HISTORY_HEAD = 8
_HISTORY_TAIL = 12
_HISTORY_ALL = _HISTORY_HEAD + _HISTORY_TAIL


def _history_lines(values: tuple[Any, ...], residuals: tuple[float, ...]) -> list[str]:
    """Render seed + iterates; omit a middle span when the trace is long."""
    lines = [f"  0: {values[0]!r}"]
    for index, (value, residual) in enumerate(zip(values[1:], residuals, strict=True), start=1):
        lines.append(f"  {index}: {value!r}  distance={residual}")
    if len(lines) <= _HISTORY_ALL:
        return lines
    omitted = len(lines) - _HISTORY_HEAD - _HISTORY_TAIL
    return [
        *lines[:_HISTORY_HEAD],
        f"  ... ({omitted} iterates omitted) ...",
        *lines[-_HISTORY_TAIL:],
    ]


def _completed(value: Any) -> Step[Any]:
    """A step that immediately completes with `value`."""
    return value
    yield  # unreachable; makes this function a generator


@dataclass(slots=True)
class _FixedPoint:
    spec: Iterate[Any]
    seed: Any
    iteration: int = 0
    written: list[RuleKey] = field(default_factory=list)
    guesses: list[Any] = field(default_factory=list)
    residuals: list[float] = field(default_factory=list)


class Context:
    def __init__(self, *, tol: float = 1e-9, max_iter: int = 100) -> None:
        self._tol = tol
        self._max_iter = max_iter
        self._compute_cache: dict[RuleKey, Any] = {}
        self._deps: dict[RuleKey, set[RuleKey]] = {}
        self._stack: list[RuleKey] = []
        self._on_stack: set[RuleKey] = set()
        self._targets: dict[int, Target] = {}
        self._pending_spec: dict[RuleKey, Iterate[Any]] = {}
        self._fp: dict[RuleKey, _FixedPoint] = {}

    def get_at[K: Hashable, V](self, rule: KeyedRule[K, V], key: K) -> V:
        return self._resolve(rule, key, lambda: rule.compute(key))

    def get[V](self, rule: Rule[V]) -> V:
        return self._resolve(rule, _UNIT, lambda: rule.compute())

    def dependencies[K: Hashable, V](self, rule: KeyedRule[K, V], key: K) -> DepNode:
        """Resolve ``rule``/``key``, then return its dependency tree."""
        self.get_at(rule, key)
        return self._dep_node((rule.id, key), seen=set())

    def rule_dependencies[V](self, rule: Rule[V]) -> DepNode:
        """Resolve ``rule``, then return its dependency tree."""
        self.get(rule)
        return self._dep_node((rule.id, _UNIT), seen=set())

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
        # frame that demanded them. Acyclic ``compute`` bodies run exactly
        # once per cell. Cyclic demands with an ``Iterate`` policy re-run the
        # cut cell until successive values are close. No Python recursion.
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
                    to_send = self._finish(finished, stop.value, frames)
                else:
                    dep_target = demanded.target
                    child: RuleKey = (dep_target.id, demanded.key)
                    self._targets[dep_target.id] = dep_target
                    self._record_dep(self._stack[-1], child)

                    dep_cached = self._compute_cache.get(child, _MISSING)
                    if dep_cached is not _MISSING:
                        to_send = dep_cached
                    elif child in self._on_stack:
                        to_send = self._cut(child, demanded.iterate)
                    else:
                        if demanded.iterate is not None:
                            self._pending_spec.setdefault(child, demanded.iterate)
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

    def _cut(self, child: RuleKey, iterate: Iterate[Any] | None) -> Any:
        spec = iterate if iterate is not None else self._pending_spec.get(child)
        if spec is None:
            self._raise_cycle(child)
        fp = self._fp.get(child)
        if fp is None:
            fp = _FixedPoint(spec=spec, seed=spec.seed, guesses=[spec.seed])
            self._fp[child] = fp
        return fp.seed

    def _finish(self, finished: RuleKey, value: Any, frames: list[Step[Any]]) -> Any:
        fp = self._fp.get(finished)
        if fp is None:
            return self._commit(finished, value)

        fp.iteration += 1
        residual = fp.spec.distance(fp.seed, value)
        fp.guesses.append(value)
        fp.residuals.append(residual)
        spec_tol = fp.spec.tol
        tol: float = self._tol if spec_tol is None else spec_tol
        spec_max_iter = fp.spec.max_iter
        max_iter: int = self._max_iter if spec_max_iter is None else spec_max_iter
        if residual < tol:
            del self._fp[finished]
            return self._commit(finished, value)
        if fp.iteration >= max_iter:
            raise ConvergenceError(
                finished,
                iterations=fp.iteration,
                residual=residual,
                tol=tol,
                values=tuple(fp.guesses),
                residuals=tuple(fp.residuals),
                names=self._target_names(),
            )
        self._invalidate(fp)
        fp.seed = value
        target = self._targets[finished[0]]
        self._push(finished, _start(target, finished[1]), frames)
        return None

    def _commit(self, finished: RuleKey, value: Any) -> Any:
        self._compute_cache[finished] = value
        self._pending_spec.pop(finished, None)
        self._note_written(finished)
        return value

    def _note_written(self, finished: RuleKey) -> None:
        for cell, state in self._fp.items():
            if cell in self._on_stack:
                state.written.append(finished)

    def _invalidate(self, fp: _FixedPoint) -> None:
        for key in fp.written:
            self._compute_cache.pop(key, None)
            self._deps.pop(key, None)
            self._pending_spec.pop(key, None)
            self._fp.pop(key, None)
        fp.written.clear()

    def _raise_cycle(self, cell: RuleKey) -> NoReturn:
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

        def sort_key(child: RuleKey) -> tuple[str, str, int]:
            return (self._targets[child[0]].name, repr(child[1]), child[0])

        children = sorted(self._deps.get(cell, ()), key=sort_key)
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
    if isinstance(target, Rule):
        return target.compute()
    return target.compute(key)
