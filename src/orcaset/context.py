# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import cast

from .cell import Cell, Point, Span
from .period import Period
from .series import PointSeriesBase, Series, SpanSeriesBase


class _SpanCache:
    __slots__ = ("series", "iterator", "spans", "_cursor_date", "_exhausted")

    def __init__(
        self,
        series: SpanSeriesBase,
        iterator: Iterator[Span],
        spans: dict[Period, Span],
    ) -> None:
        self.series = series
        self.iterator = iterator
        self.spans = spans
        # Date of last materialized span, or None if no spans have been materialized yet
        self._cursor_date: date | None = None
        self._exhausted = False

    def ensure_materialized_through(self, date: date) -> None:
        """Ensure that the cache is materialized through `date`."""
        while not self._exhausted and (self._cursor_date is None or date > self._cursor_date):
            self.materialize_next()

    def ensure_materialized_after(self, date: date) -> None:
        """Ensure that at least one materialized span ends after `date`, if possible."""
        while not self._exhausted and (self._cursor_date is None or date >= self._cursor_date):
            self.materialize_next()

    def materialize_next(self) -> None:
        try:
            next_span = next(self.iterator)
        except StopIteration:
            self._exhausted = True
            return
        if next_span.source is None:
            next_span.source = self.series
        self.spans[next_span.period] = next_span
        self._cursor_date = next_span.period.end


class CellConvergenceError(RuntimeError):
    """Raised when recursive cell formulas do not converge."""


@dataclass(frozen=True)
class CellDependencyNode:
    cell: Cell
    value: float | None


@dataclass(frozen=True)
class CellDependencyGraph:
    root: Cell
    nodes: dict[int, CellDependencyNode]
    edges: dict[int, frozenset[int]]

    def to_dot(self) -> str:
        lines = ["digraph cell_dependencies {"]
        for cell_id in sorted(self.nodes):
            node = self.nodes[cell_id]
            label = _cell_dot_label(cell_id, node)
            lines.append(f'  cell_{cell_id} [label="{label}"];')

        for source_id in sorted(self.edges):
            for dependency_id in sorted(self.edges[source_id]):
                lines.append(f"  cell_{source_id} -> cell_{dependency_id};")

        lines.append("}")
        return "\n".join(lines)


class _ResolvingCell:
    __slots__ = ("cell", "cell_id", "value")

    def __init__(self, cell: Cell, value: float | None):
        self.cell = cell
        self.cell_id = cell.id()
        self.value = value


class _ResolvedCell:
    __slots__ = ("cell", "cell_id", "value")

    def __init__(self, cell: Cell, value: float | None):
        self.cell = cell
        self.cell_id = cell.id()
        self.value = value


class Context:
    """`Context` manages all state for cell and value evaluation."""

    def __init__(self) -> None:
        self._values: dict[type[Series], Series] = {}
        self._span_cache: dict[int, _SpanCache] = {}
        self._point_cache: dict[int, dict[date, Point]] = {}
        self._family_series_types: dict[tuple[int, Hashable], type[Series]] = {}
        self._cell_values: dict[int, _ResolvingCell | _ResolvedCell] = {}
        self._solving_cells: list[Cell] = []
        self._solving_cell_ids: set[int] = set()
        self._active_cell: Cell | None = None
        self._cell_dependencies: dict[int, set[int]] = {}

    def get[T: Series](self, series_type: type[T]) -> T:
        """
        Get a series instance of type `T`.

        If an instance of type `T` already exists, return it. Otherwise,
        create a new instance and store it.

        Member series are keyed by their type hashes which makes lookups
        invariant to the series type. In other words, getting `MySeries`
        will not match against any subclass of `MySeries`.
        """

        if series_type in self._values:
            return cast(T, self._values[series_type])
        instance = series_type(self)
        self._values[series_type] = instance
        return instance

    def get_or_create_span_cache(self, series: SpanSeriesBase) -> _SpanCache:
        if series._id in self._span_cache:
            return self._span_cache[series._id]
        cache = _SpanCache(series, iter(series.spans()), {})
        self._span_cache[series._id] = cache
        return cache

    def get_or_create_point_cache(self, series: PointSeriesBase) -> dict[date, Point]:
        if series._id in self._point_cache:
            return self._point_cache[series._id]
        self._point_cache[series._id] = {}
        return self._point_cache[series._id]

    def family_series_by_key[T: Series](self, family: Series, key: Hashable) -> T | None:
        series_type = self._family_series_types.get((family._id, key))
        if series_type is None:
            return None
        return self.get(cast(type[T], series_type))

    def get_or_create_family_series[T: Series](
        self,
        family: Series,
        key: Hashable,
        factory: Callable[[], type[T]],
    ) -> T:
        cache_key = (family._id, key)
        series_type = self._family_series_types.get(cache_key)
        if series_type is None:
            series_type = factory()
            self._family_series_types[cache_key] = series_type
        return self.get(cast(type[T], series_type))

    def eval_cell(self, cell: Cell) -> float | None:
        if self._active_cell is not None:
            self._cell_dependencies.setdefault(self._active_cell.id(), set()).add(cell.id())

        cached_value = self._cell_values.get(cell.id())
        if isinstance(cached_value, _ResolvedCell):
            return cached_value.value
        if cached_value is not None and self._active_cell is not None:
            return cached_value.value

        if self._active_cell is None:
            return self.solve_cells([cell])[0]

        self._prime_cell(cell)
        return self._cell_values[cell.id()].value

    def solve_cells(
        self,
        cells: Iterable[Cell],
        *,
        tolerance: float = 1e-9,
        max_iterations: int = 1000,
    ) -> list[float | None]:
        input_cells = list(cells)
        previous_solving_cells = self._solving_cells
        previous_solving_cell_ids = self._solving_cell_ids

        self._solving_cells = []
        self._solving_cell_ids = set()
        for cell in input_cells:
            self._prime_cell(cell)

        try:
            for _ in range(1, max_iterations + 1):
                max_delta = 0.0
                index = 0

                while index < len(self._solving_cells):
                    cell = self._solving_cells[index]
                    index += 1

                    cached_value = self._cell_values[cell.id()]
                    if isinstance(cached_value, _ResolvedCell):
                        continue

                    old_value = cached_value.value
                    new_value = self._eval_cell_formula(cell)
                    cached_value.value = new_value
                    max_delta = max(max_delta, _value_delta(old_value, new_value))

                if max_delta < tolerance:
                    for cell in self._solving_cells:
                        cached_value = self._cell_values[cell.id()]
                        if isinstance(cached_value, _ResolvingCell):
                            self._cell_values[cell.id()] = _ResolvedCell(cell, cached_value.value)
                    return [self._cell_values[cell.id()].value for cell in input_cells]

            raise CellConvergenceError(
                f"Cell formulas failed to converge after {max_iterations} iterations"
            )
        finally:
            self._solving_cells = previous_solving_cells
            self._solving_cell_ids = previous_solving_cell_ids

    def deps(self, cell: Cell) -> CellDependencyGraph:
        if not isinstance(self._cell_values.get(cell.id()), _ResolvedCell):
            self.solve_cells([cell])

        nodes: dict[int, CellDependencyNode] = {}
        edges: dict[int, frozenset[int]] = {}
        pending = [cell.id()]

        while pending:
            cell_id = pending.pop()
            if cell_id in nodes:
                continue

            cached_value = self._cell_values[cell_id]
            nodes[cell_id] = CellDependencyNode(cached_value.cell, cached_value.value)

            dependency_ids = frozenset(self._cell_dependencies.get(cell_id, set()))
            edges[cell_id] = dependency_ids
            pending.extend(dependency_ids)

        return CellDependencyGraph(cell, nodes, edges)

    def _prime_cell(self, cell: Cell) -> None:
        cell_id = cell.id()
        if cell_id not in self._cell_values:
            self._cell_values[cell_id] = _ResolvingCell(cell, 0.0)
        if cell_id not in self._solving_cell_ids:
            self._solving_cells.append(cell)
            self._solving_cell_ids.add(cell_id)

    def _eval_cell_formula(self, cell: Cell) -> float | None:
        self._cell_dependencies[cell.id()] = set()
        previous_active_cell = self._active_cell
        self._active_cell = cell
        try:
            return cell.fn.eval()
        finally:
            self._active_cell = previous_active_cell


def _value_delta(old_value: float | None, new_value: float | None) -> float:
    if isinstance(old_value, int | float) and isinstance(new_value, int | float):
        return abs(float(new_value) - float(old_value))
    if old_value == new_value:
        return 0.0
    return float("inf")


def _dot_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _cell_dot_label(cell_id: int, node: CellDependencyNode) -> str:
    parts = [f"cell {cell_id}"]
    if node.cell.source is not None:
        source_type = type(node.cell.source)
        source_name = source_type.display_name()
        if source_type.label is not None and source_name != source_type.__name__:
            parts.append(f"source: {source_name} ({source_type.__name__})")
        else:
            parts.append(f"source: {source_name}")
    parts.append(f"value: {repr(node.value)}")
    return "\\n".join(_dot_escape(part) for part in parts)
