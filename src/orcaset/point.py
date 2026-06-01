# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, NamedTuple, overload

from ._value_ops import (
    ValueOp,
    add_scalar_values,
    div_scalar_values,
    div_values,
    mul_values,
    neg_values,
    rdiv_scalar_values,
    rsub_scalar_values,
    scale_values,
    sub_scalar_values,
    sub_values,
    sum_values,
)
from .cell import Point, Span
from .formula import Formula, Op
from .period import Period
from .span import SpanSeriesDef

if TYPE_CHECKING:
    from .context import Context


type PointSeriesFn = Callable[["Context", date], Formula[float | None]]
type PointSeriesKeyFn[K: Hashable] = Callable[["Context", date], Iterable[K]]
type PointSeriesFactory[K: Hashable] = Callable[[K], "PointSeriesDef"]


class PointSeriesDef(NamedTuple):
    """A date-indexed point series definition."""

    fn: PointSeriesFn
    label: str

    def query(self, ctx: "Context", dt: date) -> Point:
        """Return the point cell for `dt`, creating and caching it if needed."""
        point_cache = ctx.get_or_create_point_cache(self)
        if dt not in point_cache:
            point_cache[dt] = Point(dt, self.fn(ctx, dt), self)
        return point_cache[dt]

    def value(self, ctx: "Context", dt: date) -> Formula[float | None]:
        """Return a formula resolving this series value at `dt`."""
        return Formula(_PointValueOp(ctx, self.query(ctx, dt)))


@dataclass(slots=True)
class KeyedPointSeries[K: Hashable]:
    """A keyed collection of point series definitions."""

    key_fn: PointSeriesKeyFn[K]
    series_factory: PointSeriesFactory[K]
    label: str

    def keys(self, ctx: "Context", dt: date) -> tuple[K, ...]:
        """Return stable, de-duplicated keys for the requested date."""
        return tuple(dict.fromkeys(self.key_fn(ctx, dt)))

    def get(self, ctx: "Context", key: K) -> PointSeriesDef:
        """Return the context-cached series definition for `key`."""
        return ctx.get_or_create_keyed_point_series(self, key)

    def items(self, ctx: "Context", dt: date) -> tuple[tuple[K, PointSeriesDef], ...]:
        """Return `(key, series)` pairs for the requested date."""
        return tuple((key, self.get(ctx, key)) for key in self.keys(ctx, dt))


class _PointValueOp(Op[float | None]):
    def __init__(self, ctx: "Context", point: Point) -> None:
        self.ctx = ctx
        self.point = point

    def eval(self) -> float | None:
        return self.point.eval(self.ctx)

    def __repr__(self) -> str:
        return f"PointValueOp(point={self.point!r})"


@overload
def define(
    fn: PointSeriesFn,
    /,
    *,
    label: str | None = None,
) -> PointSeriesDef: ...


@overload
def define(
    *,
    label: str | None = None,
) -> Callable[[PointSeriesFn], PointSeriesDef]: ...


def define(
    fn: PointSeriesFn | None = None,
    /,
    *,
    label: str | None = None,
) -> PointSeriesDef | Callable[[PointSeriesFn], PointSeriesDef]:
    """Create a point series definition from a point formula function."""

    def create(fn: PointSeriesFn) -> PointSeriesDef:
        return PointSeriesDef(fn=fn, label=label or fn.__name__)

    if fn is None:
        return create

    return create(fn)


def keyed[K: Hashable](
    keys: PointSeriesKeyFn[K],
    series: PointSeriesFactory[K],
    *,
    label: str = "KeyedPointSeries",
) -> KeyedPointSeries[K]:
    """Create a keyed collection of point series definitions."""
    return KeyedPointSeries(key_fn=keys, series_factory=series, label=label)


def accumulate(
    start: date,
    value: float | None,
    changes: SpanSeriesDef,
    label: str = "AccumulatedPointSeries",
) -> PointSeriesDef:
    """Create a point series by accumulating span changes from a start value."""

    def point(ctx: "Context", dt: date) -> Formula[float | None]:
        if dt < start:
            return Formula.pure(None)
        if dt == start:
            return Formula.pure(value)

        spans = changes.query(ctx, Period(start, dt))

        def add_changes(spans: list[Span]) -> float | None:
            if value is None:
                return None

            total = 0.0
            for span in spans:
                span_value = span.eval(ctx)
                if span_value is not None:
                    total += span_value
            return value + total

        return spans.map(add_changes)

    return PointSeriesDef(fn=point, label=label)


def neg(series: PointSeriesDef, *, label: str | None = None) -> PointSeriesDef:
    """Create a point series that negates another point series."""
    return _operator(label or f"Neg{series.label}", [series], neg_values)


def scale(
    series: PointSeriesDef,
    factor: float,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series scaled by `factor`."""
    return _operator(label or f"Scale{series.label}", [series], scale_values(factor))


def add_scalar(
    series: PointSeriesDef,
    value: int | float,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series with `value` added to each point."""
    return _operator(label or f"Add{series.label}Scalar", [series], add_scalar_values(value))


def sum(
    series: Sequence[PointSeriesDef],
    *,
    label: str = "SumPointSeries",
) -> PointSeriesDef:
    """Create a point series by summing multiple point series."""
    return _operator(label, series, sum_values)


def sub(
    left: PointSeriesDef,
    right: PointSeriesDef,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series that subtracts `right` from `left`."""
    return _operator(label or f"Sub{left.label}{right.label}", [left, right], sub_values)


def sub_scalar(
    series: PointSeriesDef,
    value: int | float,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series with `value` subtracted from each point."""
    return _operator(label or f"Sub{series.label}Scalar", [series], sub_scalar_values(value))


def rsub_scalar(
    value: int | float,
    series: PointSeriesDef,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series by subtracting each point from `value`."""
    return _operator(label or f"RSubScalar{series.label}", [series], rsub_scalar_values(value))


def mul(
    series: Sequence[PointSeriesDef],
    *,
    label: str = "MulPointSeries",
) -> PointSeriesDef:
    """Create a point series by multiplying multiple point series."""
    return _operator(label, series, mul_values)


def div(
    left: PointSeriesDef,
    right: PointSeriesDef,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series that divides `left` by `right`."""
    return _operator(label or f"Div{left.label}{right.label}", [left, right], div_values)


def div_scalar(
    series: PointSeriesDef,
    value: int | float,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series that divides each point by `value`."""
    return _operator(label or f"Div{series.label}Scalar", [series], div_scalar_values(value))


def rdiv_scalar(
    value: int | float,
    series: PointSeriesDef,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series by dividing `value` by each point."""
    return _operator(label or f"RDivScalar{series.label}", [series], rdiv_scalar_values(value))


def _operator(
    label: str,
    series_defs: Sequence[PointSeriesDef],
    op: ValueOp,
) -> PointSeriesDef:
    def point(ctx: "Context", dt: date) -> Formula[float | None]:
        points = [series.query(ctx, dt) for series in series_defs]
        return Formula(_PointTupleValueOp(ctx, points, op))

    return PointSeriesDef(fn=point, label=label)


class _PointTupleValueOp(Op[float | None]):
    def __init__(self, ctx: "Context", points: Sequence[Point], op: ValueOp) -> None:
        self.ctx = ctx
        self.points = points
        self.op = op

    def eval(self) -> float | None:
        return self.op([point.eval(self.ctx) for point in self.points])

    def __repr__(self) -> str:
        return f"PointTupleValueOp(points={self.points!r})"
