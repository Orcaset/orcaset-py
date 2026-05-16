# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from typing import Iterable, Iterator, cast
from datetime import date

from .cell import Cell, Point, Span
from .period import Period
from .series import Series, SpanSeries, PointSeries


class _SpanCache:
    __slots__ = ("iterator", "spans", "_cursor_date", "_exhausted")

    def __init__(self, iterator: Iterator[Span], spans: dict[Period, Span | None]) -> None:
        self.iterator = iterator
        self.spans = spans
        # Date of last materialized span, or None if no spans have been materialized yet
        self._cursor_date: date | None = None
        self._exhausted = False

    def ensure_materialized_through(self, date: date) -> None:
        """Ensure that the cache is materialized through `date`."""
        while not self._exhausted and (self._cursor_date is None or date > self._cursor_date):
            try:
                next_span = next(self.iterator)
            except StopIteration:
                self._exhausted = True
                return
            self.spans[next_span.period] = next_span
            self._cursor_date = next_span.period.end


type CellValue = float | None


class CellConvergenceError(RuntimeError):
    """Raised when recursive cell formulas do not converge."""


class _ResolvingCell:
    __slots__ = ("cell", "cell_id", "value")

    def __init__(self, cell: Cell, value: CellValue):
        self.cell = cell
        self.cell_id = cell.id()
        self.value = value


class _ResolvedCell:
    __slots__ = ("cell", "cell_id", "value")

    def __init__(self, cell: Cell, value: CellValue):
        self.cell = cell
        self.cell_id = cell.id()
        self.value = value


class Context:
    """`Context` manages all state for cell and value evaluation."""

    def __init__(self) -> None:
        self._values: dict[type[Series], Series] = {}
        self._span_cache: dict[int, _SpanCache] = {}
        self._point_cache: dict[int, dict[date, Point | None]] = {}
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

    def get_or_create_span_cache(self, series: SpanSeries) -> _SpanCache:
        if series._id in self._span_cache:
            return self._span_cache[series._id]
        cache = _SpanCache(iter(series.spans()), {})
        self._span_cache[series._id] = cache
        return cache

    def get_or_create_point_cache(self, series: PointSeries) -> dict[date, Point | None]:
        if series._id in self._point_cache:
            return self._point_cache[series._id]
        self._point_cache[series._id] = {}
        return self._point_cache[series._id]

    def eval_cell(self, cell: Cell) -> CellValue:
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
    ) -> list[CellValue]:
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

    def _prime_cell(self, cell: Cell) -> None:
        cell_id = cell.id()
        if cell_id not in self._cell_values:
            self._cell_values[cell_id] = _ResolvingCell(cell, 0.0)
        if cell_id not in self._solving_cell_ids:
            self._solving_cells.append(cell)
            self._solving_cell_ids.add(cell_id)

    def _eval_cell_formula(self, cell: Cell) -> CellValue:
        self._cell_dependencies[cell.id()] = set()
        previous_active_cell = self._active_cell
        self._active_cell = cell
        try:
            return cell.fn.eval()
        finally:
            self._active_cell = previous_active_cell


def _value_delta(old_value: CellValue, new_value: CellValue) -> float:
    if isinstance(old_value, int | float) and isinstance(new_value, int | float):
        return abs(float(new_value) - float(old_value))
    if old_value == new_value:
        return 0.0
    return float("inf")
