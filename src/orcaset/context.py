# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Generator, Hashable
from dataclasses import dataclass, field
from typing import Any, NoReturn, cast

from orcaset.rule import _UNIT, Effect, Iterate, KeyedRule, Rule

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
    to see oscillation, blow-up, or a slow crawl. ``seeded_residuals`` holds
    the last residual and tolerance for every seeded cell observed this
    iteration. ``unobserved`` names seeded cells that were not demanded.
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
        seeded_residuals: tuple[tuple[RuleKey, float, float], ...] = (),
        unobserved: tuple[RuleKey, ...] = (),
    ) -> None:
        self.cell = cell
        self.iterations = iterations
        self.residual = residual
        self.tol = tol
        self.values = values
        self.residuals = residuals
        self.seeded_residuals = seeded_residuals
        self.unobserved = unobserved
        names = names or {}
        label = _format_cell(names.get(cell[0], str(cell[0])), cell[1])
        history = _history_lines(values, residuals)
        if len(seeded_residuals) <= 1 and not unobserved:
            lines = [
                (
                    f"Failed to converge {label} after {iterations} iterations "
                    f"(distance={residual}, tol={tol})"
                ),
                *history,
            ]
        else:
            lines = [f"Failed to converge after {iterations} iterations"]
            for seeded_cell, seeded_residual, seeded_tol in seeded_residuals:
                seeded_label = _format_cell(
                    names.get(seeded_cell[0], str(seeded_cell[0])), seeded_cell[1]
                )
                met = "met" if seeded_residual < seeded_tol else "not met"
                lines.append(
                    f"  {seeded_label}: distance={seeded_residual}, tol={seeded_tol} ({met})"
                )
            for missing in unobserved:
                missing_label = _format_cell(
                    names.get(missing[0], str(missing[0])), missing[1]
                )
                lines.append(f"  {missing_label}: not observed this iteration")
            lines.append(f"  cut {label}:")
            lines.extend(history)
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


def _completed(value: Any) -> Effect[Any]:
    """A step that immediately completes with `value`."""
    return value
    yield  # unreachable; makes this function a generator


@dataclass(slots=True)
class _FixedPoint:
    cut: RuleKey
    specs: dict[RuleKey, Iterate[Any]]
    prev: dict[RuleKey, Any]
    iteration: int = 0
    written: list[RuleKey] = field(default_factory=list)
    guesses: list[Any] = field(default_factory=list)
    residuals: list[float] = field(default_factory=list)
    last_residuals: dict[RuleKey, float] = field(default_factory=dict)
    unobserved: tuple[RuleKey, ...] = ()


class Context:
    def __init__(self, *, tol: float = 1e-9, max_iter: int = 1000) -> None:
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

    def dependencies[K: Hashable, V](
        self,
        rule: KeyedRule[K, V],
        key: K,
        *,
        structural: bool = False,
    ) -> DepNode:
        """Resolve a keyed rule, then return its dependency tree.

        Internal chain traversal rules are folded by default. Pass
        ``structural=True`` for the full scheduler-level tree.
        """
        self.get_at(rule, key)
        return self._dep_node((rule.id, key), seen=set(), structural=structural)

    def rule_dependencies[V](self, rule: Rule[V], *, structural: bool = False) -> DepNode:
        """Resolve an unkeyed rule, then return its dependency tree."""
        self.get(rule)
        return self._dep_node((rule.id, _UNIT), seen=set(), structural=structural)

    def _resolve[V](
        self,
        target: Target,
        key: Hashable,
        compute: Callable[[], Effect[V] | V],
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
        # once per cell. On a cycle, any executed ``Iterate`` spec in the
        # component can cut it; the scheduler iterates until every seeded
        # cell observed this iteration is within its tolerance.
        stack_start = len(self._stack)
        frames: list[Effect[Any]] = []
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
                    to_send = self._commit(finished, stop.value)
                else:
                    dep_target = demanded.target
                    child: RuleKey = (dep_target.id, demanded.key)
                    self._targets[dep_target.id] = dep_target
                    self._record_dep(self._stack[-1], child)

                    dep_cached = self._compute_cache.get(child, _MISSING)
                    if dep_cached is not _MISSING:
                        to_send = dep_cached
                    elif child in self._on_stack:
                        to_send = self._on_cycle(child, demanded.iterate, frames, stack_start)
                        if not frames:
                            break
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

    def _push(self, cell: RuleKey, result: Effect[Any] | Any, frames: list[Effect[Any]]) -> None:
        self._stack.append(cell)
        self._on_stack.add(cell)
        if isinstance(result, Generator):
            frames.append(result)
        else:
            frames.append(_completed(result))

    def _on_cycle(
        self,
        child: RuleKey,
        iterate: Iterate[Any] | None,
        frames: list[Effect[Any]],
        stack_start: int,
    ) -> Any:
        cycle_start = self._stack.index(child)
        cycle = list(self._stack[cycle_start:])
        specs = self._cycle_specs(cycle, child, iterate)
        fp = self._fp.get(child)
        if fp is not None:
            # Already iterating this cut: inject the current guess even if
            # this back-edge has no spec (pending_spec is popped on commit).
            return self._inject(fp, specs)
        if not specs:
            self._raise_cycle(child)
        if cycle_start < stack_start:
            self._raise_cycle(child)
        self._unwind(cycle_start, frames)
        cut = child if child in specs else next(cell for cell in reversed(cycle) if cell in specs)
        return self._iterate_scc(child, cut, specs)

    def _cycle_specs(
        self,
        cycle: list[RuleKey],
        back_edge_target: RuleKey,
        back_edge_iterate: Iterate[Any] | None,
    ) -> dict[RuleKey, Iterate[Any]]:
        specs: dict[RuleKey, Iterate[Any]] = {}
        for cell in cycle:
            pending = self._pending_spec.get(cell)
            if pending is not None:
                specs[cell] = pending
        if back_edge_iterate is not None:
            specs[back_edge_target] = back_edge_iterate
        return specs

    def _unwind(self, cycle_start: int, frames: list[Effect[Any]]) -> None:
        while len(self._stack) > cycle_start:
            frames[-1].close()
            frames.pop()
            self._on_stack.discard(self._stack.pop())

    def _inject(self, fp: _FixedPoint, specs: dict[RuleKey, Iterate[Any]]) -> Any:
        for cell, spec in specs.items():
            if cell not in fp.specs:
                fp.specs[cell] = spec
                fp.prev[cell] = spec.seed
        return fp.prev[fp.cut]

    def _iterate_scc(
        self,
        entry: RuleKey,
        cut: RuleKey,
        specs: dict[RuleKey, Iterate[Any]],
    ) -> Any:
        # One iterate driver for every cycle. When the cut is the entry, the
        # guess is injected on the back-edge (_inject) because caching the cut
        # would make eval(cut) return the guess without running the formula.
        # When the cut is a descendant, the guess is cached so the rest of the
        # component is a DAG, then the cut is recomputed.
        fp = _FixedPoint(
            cut=cut,
            specs=dict(specs),
            prev={cell: spec.seed for cell, spec in specs.items()},
            guesses=[specs[cut].seed],
        )
        self._fp[cut] = fp
        try:
            while True:
                if entry == cut:
                    self._invalidate(fp)
                    new_cut = self._eval_cell(cut)
                else:
                    self._compute_cache[cut] = fp.prev[cut]
                    self._invalidate(fp, keep=cut)
                    self._eval_cell(entry)
                    self._compute_cache.pop(cut, None)
                    new_cut = self._eval_cell(cut)
                new_vals = self._seeded_values(fp, new_cut)
                if self._record_iterate(fp, new_vals):
                    self._fp.pop(cut, None)
                    self._freeze(fp)
                    return self._eval_cell(entry)
                if fp.iteration >= self._max_iters(fp, new_vals):
                    raise self._convergence_error(fp)
        finally:
            self._fp.pop(cut, None)

    def _seeded_values(self, fp: _FixedPoint, cut_value: Any) -> dict[RuleKey, Any]:
        values = {fp.cut: cut_value}
        for cell in fp.specs:
            if cell == fp.cut:
                continue
            cached = self._compute_cache.get(cell, _MISSING)
            if cached is not _MISSING:
                values[cell] = cached
        return values

    def _record_iterate(self, fp: _FixedPoint, new_vals: dict[RuleKey, Any]) -> bool:
        fp.iteration += 1
        fp.guesses.append(new_vals[fp.cut])
        last: dict[RuleKey, float] = {}
        unobserved: list[RuleKey] = []
        converged = True
        for cell, spec in fp.specs.items():
            if cell not in new_vals:
                unobserved.append(cell)
                continue
            residual = spec.distance(fp.prev[cell], new_vals[cell])
            last[cell] = residual
            if cell == fp.cut:
                fp.residuals.append(residual)
            if residual >= self._spec_tol(spec):
                converged = False
        fp.last_residuals = last
        fp.unobserved = tuple(unobserved)
        if not converged:
            fp.prev = {**fp.prev, **new_vals}
        return converged

    def _freeze(self, fp: _FixedPoint) -> None:
        to_recompute = [key for key in fp.written if key != fp.cut]
        fp.written.clear()
        for key in to_recompute:
            self._compute_cache.pop(key, None)
            self._deps.pop(key, None)
            self._pending_spec.pop(key, None)
        for key in to_recompute:
            if self._compute_cache.get(key, _MISSING) is _MISSING:
                self._eval_cell(key)

    def _eval_cell(self, cell: RuleKey) -> Any:
        cached = self._compute_cache.get(cell, _MISSING)
        if cached is not _MISSING:
            return cached
        target = self._targets[cell[0]]
        return self._resolve(target, cell[1], lambda: _start(target, cell[1]))

    def _commit(self, finished: RuleKey, value: Any) -> Any:
        self._compute_cache[finished] = value
        self._pending_spec.pop(finished, None)
        self._note_written(finished)
        return value

    def _note_written(self, finished: RuleKey) -> None:
        for state in self._fp.values():
            state.written.append(finished)

    def _invalidate(self, fp: _FixedPoint, *, keep: RuleKey | None = None) -> None:
        kept: list[RuleKey] = []
        for key in fp.written:
            if key == keep:
                kept.append(key)
                continue
            self._compute_cache.pop(key, None)
            self._deps.pop(key, None)
            self._pending_spec.pop(key, None)
            if key != fp.cut:
                self._fp.pop(key, None)
        fp.written = kept

    def _spec_tol(self, spec: Iterate[Any]) -> float:
        return self._tol if spec.tol is None else spec.tol

    def _max_iters(self, fp: _FixedPoint, observed: dict[RuleKey, Any]) -> int:
        specs = [fp.specs[cell] for cell in observed if cell in fp.specs]
        if not specs:
            specs = [fp.specs[fp.cut]]
        return min(self._max_iter if spec.max_iter is None else spec.max_iter for spec in specs)

    def _convergence_error(self, fp: _FixedPoint) -> ConvergenceError:
        cut_spec = fp.specs[fp.cut]
        seeded = tuple(
            (cell, fp.last_residuals[cell], self._spec_tol(spec))
            for cell, spec in fp.specs.items()
            if cell in fp.last_residuals
        )
        return ConvergenceError(
            fp.cut,
            iterations=fp.iteration,
            residual=fp.residuals[-1],
            tol=self._spec_tol(cut_spec),
            values=tuple(fp.guesses),
            residuals=tuple(fp.residuals),
            names=self._target_names(),
            seeded_residuals=seeded,
            unobserved=fp.unobserved,
        )

    def _raise_cycle(self, cell: RuleKey) -> NoReturn:
        cycle_start = self._stack.index(cell)
        path = tuple(self._stack[cycle_start:])
        raise CycleError(path, names=self._target_names())

    def _dep_node(
        self,
        cell: RuleKey,
        *,
        seen: set[RuleKey],
        structural: bool,
    ) -> DepNode:
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
            deps=tuple(
                node
                for child in children
                for node in self._dep_children(child, seen=seen, structural=structural)
            ),
        )

    def _dep_children(
        self,
        cell: RuleKey,
        *,
        seen: set[RuleKey],
        structural: bool,
    ) -> tuple[DepNode, ...]:
        target = self._targets[cell[0]]
        if structural or not target.structural:
            return (self._dep_node(cell, seen=seen, structural=structural),)
        if cell in seen:
            return ()
        seen = seen | {cell}

        def sort_key(child: RuleKey) -> tuple[str, str, int]:
            return (self._targets[child[0]].name, repr(child[1]), child[0])

        children = sorted(self._deps.get(cell, ()), key=sort_key)
        return tuple(
            node
            for child in children
            for node in self._dep_children(child, seen=seen, structural=structural)
        )

    def _target_names(self) -> dict[int, str]:
        return {k: v.name for k, v in self._targets.items()}

    def _record_dep(self, consumer: RuleKey, dependency: RuleKey) -> None:
        self._deps.setdefault(consumer, set()).add(dependency)


def _start(target: Target, key: Hashable) -> Effect[Any] | Any:
    if isinstance(target, Rule):
        return target.compute()
    return target.compute(key)
