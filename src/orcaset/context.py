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


@dataclass(frozen=True, slots=True)
class JacobiTurn:
    """Snapshot of every Jacobi unknown after one sweep.

    ``index`` 0 is the seed vector. Later turns are the values computed from
    the previous turn only (true Jacobi: no same-sweep updates). ``residuals``
    maps each unknown's display name to ``distance(prev, curr)`` and is empty
    on turn 0.
    """

    index: int
    values: dict[str, Any]
    residuals: dict[str, float]


class ConvergenceError(RuntimeError):
    """Raised when a Jacobi system does not converge within ``max_iter`` turns.

    ``turns`` is the inspectable trace: ``err.turns[k].values`` is the unknown
    vector after turn ``k`` (turn 0 is the seed). Use it to see oscillation,
    blow-up, or a slow crawl.
    """

    def __init__(
        self,
        *,
        turns: tuple[JacobiTurn, ...],
        iterations: int,
        residual: float,
        tol: float,
    ) -> None:
        self.turns = turns
        self.iterations = iterations
        self.residual = residual
        self.tol = tol
        last = turns[-1] if turns else JacobiTurn(index=-1, values={}, residuals={})
        details: list[str] = []
        for name, value in last.values.items():
            turn_residual = last.residuals.get(name)
            if turn_residual is None:
                details.append(f"  {name}: {value!r}")
            else:
                details.append(f"  {name}: {value!r}  distance={turn_residual}")
        lines = [
            (
                f"Failed to converge after {iterations} Jacobi turns "
                f"(max distance={residual}, tol={tol})"
            ),
            *details,
            "Inspect ConvergenceError.turns for every unknown on every turn.",
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


def _completed(value: Any) -> Step[Any]:
    """A step that immediately completes with `value`."""
    return value
    yield  # unreachable; makes this function a generator


@dataclass(slots=True)
class _Jacobi:
    prev: dict[RuleKey, Any] = field(default_factory=dict)
    specs: dict[RuleKey, Iterate[Any]] = field(default_factory=dict)
    order: list[RuleKey] = field(default_factory=list)
    stable: set[RuleKey] = field(default_factory=set)
    turns: list[JacobiTurn] = field(default_factory=list)


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
        self._jacobi: _Jacobi | None = None

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
        # Yielded ``Demand``s resolve from cache, from the previous Jacobi
        # snapshot, or by pushing a new frame. Acyclic bodies run once. A
        # cyclic demand with an ``Iterate`` policy enrolls every seeded
        # unknown and Jacobi-sweeps them: each turn reads only the previous
        # snapshot. No Python recursion.
        run_jacobi = self._drive(cell, compute())
        if run_jacobi:
            self._jacobi_loop()
            cached = self._compute_cache.get(cell, _MISSING)
            if cached is not _MISSING:
                return cast(V, cached)
            return self._resolve(target, key, compute)

        return cast(V, self._compute_cache[cell])

    def _drive(self, root: RuleKey, started: Step[Any] | Any) -> bool:
        """Run the stack until ``root`` completes, or a Jacobi system is enrolled.

        Returns True when the caller should Jacobi-sweep enrolled unknowns.
        """
        stack_start = len(self._stack)
        frames: list[Step[Any]] = []
        self._push(root, started, frames)
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
                    self._pending_spec.pop(finished, None)
                    to_send = stop.value
                else:
                    dep_target = demanded.target
                    child: RuleKey = (dep_target.id, demanded.key)
                    self._targets[dep_target.id] = dep_target
                    self._record_dep(self._stack[-1], child)

                    dep_cached = self._compute_cache.get(child, _MISSING)
                    if dep_cached is not _MISSING:
                        to_send = dep_cached
                        continue

                    jacobi = self._jacobi
                    if jacobi is not None and child in jacobi.prev:
                        to_send = jacobi.prev[child]
                        continue

                    if child in self._on_stack:
                        if not self._prime_unknown(child, demanded.iterate):
                            self._raise_cycle(child)
                        for stacked in self._stack:
                            pending = self._pending_spec.get(stacked)
                            if pending is not None:
                                self._prime_unknown(stacked, pending)
                        return True

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
        return False

    def _push(self, cell: RuleKey, result: Step[Any] | Any, frames: list[Step[Any]]) -> None:
        self._stack.append(cell)
        self._on_stack.add(cell)
        if isinstance(result, Generator):
            frames.append(result)
        else:
            frames.append(_completed(result))

    def _prime_unknown(self, cell: RuleKey, iterate: Iterate[Any] | None) -> bool:
        spec = iterate if iterate is not None else self._pending_spec.get(cell)
        if spec is None:
            return False
        if self._jacobi is None:
            self._jacobi = _Jacobi()
        if cell not in self._jacobi.prev:
            self._jacobi.prev[cell] = spec.seed
            self._jacobi.specs[cell] = spec
            self._jacobi.order.append(cell)
        return True

    def _jacobi_loop(self) -> None:
        state = self._jacobi
        if state is None:
            raise RuntimeError("Jacobi loop started with no unknowns")
        state.stable = set(self._compute_cache)
        state.turns.append(self._jacobi_turn(0, {}))
        max_iter = self._jacobi_max_iter(state)
        try:
            for turn in range(1, max_iter + 1):
                curr: dict[RuleKey, Any] = {}
                index = 0
                while index < len(state.order):
                    cell = state.order[index]
                    index += 1
                    curr[cell] = self._eval_unknown(cell)
                residuals = {
                    cell: state.specs[cell].distance(state.prev[cell], curr[cell])
                    for cell in state.order
                }
                state.prev = curr
                state.turns.append(self._jacobi_turn(turn, residuals))
                if self._jacobi_converged(state, residuals):
                    for cell, value in curr.items():
                        self._compute_cache[cell] = value
                        self._pending_spec.pop(cell, None)
                    return
                self._drop_ephemeral(state)
            last = state.turns[-1]
            residual = max(last.residuals.values(), default=float("inf"))
            raise ConvergenceError(
                turns=tuple(state.turns),
                iterations=max_iter,
                residual=residual,
                tol=self._jacobi_message_tol(state),
            )
        finally:
            self._jacobi = None

    def _eval_unknown(self, cell: RuleKey) -> Any:
        target = self._targets[cell[0]]
        stack_start = len(self._stack)
        frames: list[Step[Any]] = []
        self._push(cell, _start(target, cell[1]), frames)
        to_send: Any = None
        try:
            while frames:
                try:
                    demanded = frames[-1].send(to_send)
                except StopIteration as stop:
                    finished = self._stack.pop()
                    self._on_stack.discard(finished)
                    frames.pop()
                    if finished == cell and not frames:
                        return stop.value
                    self._compute_cache[finished] = stop.value
                    self._pending_spec.pop(finished, None)
                    to_send = stop.value
                else:
                    dep_target = demanded.target
                    child: RuleKey = (dep_target.id, demanded.key)
                    self._targets[dep_target.id] = dep_target
                    self._record_dep(self._stack[-1], child)

                    dep_cached = self._compute_cache.get(child, _MISSING)
                    if dep_cached is not _MISSING:
                        to_send = dep_cached
                        continue

                    jacobi = self._jacobi
                    if jacobi is not None and child in jacobi.prev:
                        to_send = jacobi.prev[child]
                        continue

                    if child in self._on_stack:
                        if not self._prime_unknown(child, demanded.iterate):
                            self._raise_cycle(child)
                        jacobi = self._jacobi
                        if jacobi is None:
                            self._raise_cycle(child)
                        to_send = jacobi.prev[child]
                        continue

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
        raise RuntimeError(f"Jacobi unknown {cell!r} produced no value")

    def _drop_ephemeral(self, state: _Jacobi) -> None:
        for key in list(self._compute_cache):
            if key not in state.stable:
                self._compute_cache.pop(key, None)
                self._deps.pop(key, None)
                self._pending_spec.pop(key, None)

    def _jacobi_turn(self, index: int, residuals: dict[RuleKey, float]) -> JacobiTurn:
        state = self._jacobi
        if state is None:
            raise RuntimeError("Jacobi snapshot taken with no unknowns")
        names = self._target_names()
        values = {_format_cell(names[cell[0]], cell[1]): state.prev[cell] for cell in state.order}
        named_residuals = {
            _format_cell(names[cell[0]], cell[1]): residual for cell, residual in residuals.items()
        }
        return JacobiTurn(index=index, values=values, residuals=named_residuals)

    def _jacobi_converged(self, state: _Jacobi, residuals: dict[RuleKey, float]) -> bool:
        for cell, residual in residuals.items():
            spec_tol = state.specs[cell].tol
            tol: float = self._tol if spec_tol is None else spec_tol
            if residual >= tol:
                return False
        return True

    def _jacobi_max_iter(self, state: _Jacobi) -> int:
        limits = [
            self._max_iter if spec.max_iter is None else spec.max_iter
            for spec in state.specs.values()
        ]
        return min(limits) if limits else self._max_iter

    def _jacobi_message_tol(self, state: _Jacobi) -> float:
        tols: list[float] = []
        for spec in state.specs.values():
            tols.append(self._tol if spec.tol is None else spec.tol)
        return min(tols) if tols else self._tol

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
