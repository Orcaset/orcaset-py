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
from .span import SpanSeriesRef

if TYPE_CHECKING:
    from .context import Context


type PointSeriesFn = Callable[["Context", date], Formula[float | None]]
type PointSeriesKeyFn[K: Hashable] = Callable[[date], Iterable[K]]
type PointSeriesFactory[K: Hashable] = Callable[[K], "PointSeriesDef"]
type PointSeriesRef = PointSeriesDef | Callable[[], PointSeriesDef]


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

    def keys(self, dt: date) -> tuple[K, ...]:
        """Return stable, de-duplicated keys for the requested date."""
        return tuple(dict.fromkeys(self.key_fn(dt)))

    def get(self, ctx: "Context", key: K) -> PointSeriesDef:
        """Return the context-cached series definition for `key`."""
        return ctx.get_or_create_keyed_point_series(self, key)

    def items(self, ctx: "Context", dt: date) -> tuple[tuple[K, PointSeriesDef], ...]:
        """Return `(key, series)` pairs for the requested date."""
        return tuple((key, self.get(ctx, key)) for key in self.keys(dt))


class _PointValueOp(Op[float | None]):
    def __init__(self, ctx: "Context", point: Point) -> None:
        self.ctx = ctx
        self.point = point

    def eval(self) -> float | None:
        return self.point.eval(self.ctx)

    def __repr__(self) -> str:
        return f"PointValueOp(point={self.point!r})"


@dataclass(slots=True)
class _SeriesRef[T]:
    ref: T | Callable[[], T]
    _values: list[T]

    def __init__(self, ref: T | Callable[[], T]) -> None:
        self.ref = ref
        self._values = []

    def get(self) -> T:
        if not self._values:
            if callable(self.ref):
                self._values.append(self.ref())
            else:
                self._values.append(self.ref)
        return self._values[0]


def _ref_label(ref: PointSeriesRef, fallback: str) -> str:
    if isinstance(ref, PointSeriesDef):
        return ref.label
    return fallback


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
    changes: SpanSeriesRef,
    label: str = "AccumulatedPointSeries",
) -> PointSeriesDef:
    """Create a point series by accumulating span changes from a start value."""
    changes_ref = _SeriesRef(changes)

    def point(ctx: "Context", dt: date) -> Formula[float | None]:
        if dt < start:
            return Formula.pure(None)
        if dt == start:
            return Formula.pure(value)

        spans = changes_ref.get().query(ctx, Period(start, dt))

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


def neg(series: PointSeriesRef, *, label: str | None = None) -> PointSeriesDef:
    """Create a point series that negates another point series."""
    return _operator(label or f"Neg{_ref_label(series, 'PointSeries')}", [series], neg_values)


def scale(
    series: PointSeriesRef,
    factor: float,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series scaled by `factor`."""
    return _operator(label or f"Scale{_ref_label(series, 'PointSeries')}", [series], scale_values(factor))


def add_scalar(
    series: PointSeriesRef,
    value: int | float,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series with `value` added to each point."""
    return _operator(
        label or f"Add{_ref_label(series, 'PointSeries')}Scalar",
        [series],
        add_scalar_values(value),
    )


def sum(
    series: Sequence[PointSeriesRef],
    *,
    label: str = "SumPointSeries",
) -> PointSeriesDef:
    """Create a point series by summing multiple point series."""
    return _operator(label, series, sum_values)


def sub(
    left: PointSeriesRef,
    right: PointSeriesRef,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series that subtracts `right` from `left`."""
    return _operator(
        label
        or f"Sub{_ref_label(left, 'LeftPointSeries')}{_ref_label(right, 'RightPointSeries')}",
        [left, right],
        sub_values,
    )


def sub_scalar(
    series: PointSeriesRef,
    value: int | float,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series with `value` subtracted from each point."""
    return _operator(
        label or f"Sub{_ref_label(series, 'PointSeries')}Scalar",
        [series],
        sub_scalar_values(value),
    )


def rsub_scalar(
    value: int | float,
    series: PointSeriesRef,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series by subtracting each point from `value`."""
    return _operator(
        label or f"RSubScalar{_ref_label(series, 'PointSeries')}",
        [series],
        rsub_scalar_values(value),
    )


def mul(
    series: Sequence[PointSeriesRef],
    *,
    label: str = "MulPointSeries",
) -> PointSeriesDef:
    """Create a point series by multiplying multiple point series."""
    return _operator(label, series, mul_values)


def div(
    left: PointSeriesRef,
    right: PointSeriesRef,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series that divides `left` by `right`."""
    return _operator(
        label
        or f"Div{_ref_label(left, 'LeftPointSeries')}{_ref_label(right, 'RightPointSeries')}",
        [left, right],
        div_values,
    )


def div_scalar(
    series: PointSeriesRef,
    value: int | float,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series that divides each point by `value`."""
    return _operator(
        label or f"Div{_ref_label(series, 'PointSeries')}Scalar",
        [series],
        div_scalar_values(value),
    )


def rdiv_scalar(
    value: int | float,
    series: PointSeriesRef,
    *,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series by dividing `value` by each point."""
    return _operator(
        label or f"RDivScalar{_ref_label(series, 'PointSeries')}",
        [series],
        rdiv_scalar_values(value),
    )


def _operator(
    label: str,
    series_defs: Sequence[PointSeriesRef],
    op: ValueOp,
) -> PointSeriesDef:
    series_refs = tuple(_SeriesRef(series) for series in series_defs)

    def point(ctx: "Context", dt: date) -> Formula[float | None]:
        points = [series.get().query(ctx, dt) for series in series_refs]
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
