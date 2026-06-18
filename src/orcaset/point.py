# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Iterator, Sequence
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
from .span import SpanSeriesRef, _iter_cached_spans

if TYPE_CHECKING:
    from .context import Context


type PointSeriesFn = Callable[["Context"], Iterable[Point]]
type PointInterpolationFn = Callable[["Context", date], Formula[float | None]]
type PointSeriesKeyFn[K: Hashable] = Callable[[date], Iterable[K]]
type PointSeriesFactory[K: Hashable] = Callable[[K], "PointSeriesDef"]
type PointSeriesRef = PointSeriesDef | Callable[[], PointSeriesDef]


class PointCoverageError(ValueError):
    """Raised when a point series has no value for a requested date."""


class PointSeriesDef(NamedTuple):
    """A date-indexed point timeline definition."""

    fn: PointSeriesFn
    interpolate: PointInterpolationFn
    label: str

    def query(self, ctx: "Context", dt: date) -> Point:
        """Return the source or interpolated point cell for `dt`."""
        point_cache = ctx.get_or_create_point_cache(self)
        point = point_cache.get_point(dt)
        if point is not None:
            return point

        point_cache.ensure_materialized_at_or_after(dt)
        source_point = point_cache.get_source_point(dt)
        if source_point is not None:
            return source_point

        return point_cache.get_or_add_derived_point(Point(dt, self.interpolate(ctx, dt), self))

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


def no_interpolation(_: "Context", __: date) -> Formula[float | None]:
    """Return `None` for dates that are not yielded by the point source timeline."""
    return Formula.pure(None)


def fail_interpolation(_: "Context", dt: date) -> Formula[float | None]:
    """Raise when a date is not yielded by the point source timeline."""
    raise PointCoverageError(f"No point value available for {dt.isoformat()}")


def source_point(ctx: "Context", series: PointSeriesDef, dt: date) -> Point | None:
    """Return the exact source point at `dt`, if the series yields one."""
    point_cache = ctx.get_or_create_point_cache(series)
    point_cache.ensure_materialized_at_or_after(dt)
    return point_cache.get_source_point(dt)


def previous_point(ctx: "Context", series: PointSeriesDef, dt: date) -> Point | None:
    """Return the nearest source point before `dt`, if one exists."""
    point_cache = ctx.get_or_create_point_cache(series)
    point_cache.ensure_materialized_at_or_after(dt)
    points = [point for point in point_cache.source_points.values() if point.dt < dt]
    return max(points, key=lambda point: point.dt) if points else None


def next_point(ctx: "Context", series: PointSeriesDef, dt: date) -> Point | None:
    """Return the nearest source point after `dt`, if one exists."""
    point_cache = ctx.get_or_create_point_cache(series)
    point_cache.ensure_materialized_after(dt)
    points = [point for point in point_cache.source_points.values() if point.dt > dt]
    return min(points, key=lambda point: point.dt) if points else None


def is_exhausted_after(ctx: "Context", series: PointSeriesDef, dt: date) -> bool:
    """Return whether the source timeline has no point after `dt`."""
    point_cache = ctx.get_or_create_point_cache(series)
    point_cache.ensure_materialized_after(dt)
    return point_cache.exhausted


def iter_source_points(ctx: "Context", series: PointSeriesDef) -> Iterator[Point]:
    """Yield source points, materializing the source timeline as needed."""
    point_cache = ctx.get_or_create_point_cache(series)
    yield from point_cache.iter_source_points()


def _ref_label(ref: PointSeriesRef, fallback: str) -> str:
    if isinstance(ref, PointSeriesDef):
        return ref.label
    return fallback


@overload
def define(
    fn: PointSeriesFn,
    /,
    *,
    interpolate: PointInterpolationFn | None = None,
    label: str | None = None,
) -> PointSeriesDef: ...


@overload
def define(
    *,
    interpolate: PointInterpolationFn | None = None,
    label: str | None = None,
) -> Callable[[PointSeriesFn], PointSeriesDef]: ...


def define(
    fn: PointSeriesFn | None = None,
    /,
    *,
    interpolate: PointInterpolationFn | None = None,
    label: str | None = None,
) -> PointSeriesDef | Callable[[PointSeriesFn], PointSeriesDef]:
    """Create a point series definition from a point source timeline."""
    interpolation = interpolate or no_interpolation

    def create(fn: PointSeriesFn) -> PointSeriesDef:
        return PointSeriesDef(fn=fn, interpolate=interpolation, label=label or fn.__name__)

    if fn is None:
        return create

    return create(fn)


@overload
def derived(
    interpolate: PointInterpolationFn,
    /,
    *,
    label: str | None = None,
) -> PointSeriesDef: ...


@overload
def derived(
    *,
    label: str | None = None,
) -> Callable[[PointInterpolationFn], PointSeriesDef]: ...


def derived(
    interpolate: PointInterpolationFn | None = None,
    /,
    *,
    label: str | None = None,
) -> PointSeriesDef | Callable[[PointInterpolationFn], PointSeriesDef]:
    """Create a point series whose values are entirely produced by interpolation."""

    def create(interpolate: PointInterpolationFn) -> PointSeriesDef:
        def points(_: "Context") -> Iterable[Point]:
            return ()

        return PointSeriesDef(
            fn=points, interpolate=interpolate, label=label or interpolate.__name__
        )

    if interpolate is None:
        return create

    return create(interpolate)


def keyed[K: Hashable](
    keys: PointSeriesKeyFn[K],
    series: PointSeriesFactory[K],
    *,
    label: str = "KeyedPointSeries",
) -> KeyedPointSeries[K]:
    """Create a keyed collection of point series definitions."""
    return KeyedPointSeries(key_fn=keys, series_factory=series, label=label)


def from_list(
    values: Iterable[tuple[date, float | None]],
    *,
    interpolate: PointInterpolationFn = no_interpolation,
    label: str = "ListPointSeries",
) -> PointSeriesDef:
    """Create a point series from explicit date value records."""
    records = tuple(values)

    def points(_: "Context") -> Iterable[Point]:
        for dt, value in records:
            yield Point(dt, Formula.pure(value))

    return PointSeriesDef(fn=points, interpolate=interpolate, label=label)


def constant(
    value: float | None,
    *,
    start: date | None = None,
    end: date | None = None,
    label: str | None = None,
) -> PointSeriesDef:
    """Create a point series with a constant value over an optional date range."""
    start_date = start or date.min
    if end is not None and start_date >= end:
        raise ValueError("constant start must be before end")

    def points(_: "Context") -> Iterable[Point]:
        yield Point(start_date, Formula.pure(value))
        if end is not None:
            yield Point(end, Formula.pure(None))

    def interpolate(_: "Context", dt: date) -> Formula[float | None]:
        if dt < start_date:
            return Formula.pure(None)
        if end is not None and dt >= end:
            return Formula.pure(None)
        return Formula.pure(value)

    return PointSeriesDef(
        fn=points,
        interpolate=interpolate,
        label=label or "ConstantPointSeries",
    )


def extend(
    base: PointSeriesRef,
    *,
    interpolate: PointInterpolationFn,
    label: str | None = None,
) -> Callable[[Callable[["Context", date], Iterable[Point]]], PointSeriesDef]:
    """Create a decorator that extends `base` with continuation points."""
    base_ref = _SeriesRef(base)

    def decorator(
        continuation: Callable[["Context", date], Iterable[Point]],
    ) -> PointSeriesDef:
        def points(ctx: "Context") -> Iterable[Point]:
            last_dt: date | None = None

            for point in iter_source_points(ctx, base_ref.get()):
                last_dt = point.dt
                yield point

            if last_dt is not None:
                yield from continuation(ctx, last_dt)

        return PointSeriesDef(
            fn=points,
            interpolate=interpolate,
            label=label or continuation.__name__,
        )

    return decorator


def carry_forward(series: PointSeriesRef) -> PointInterpolationFn:
    """Create an interpolation function that uses the nearest prior source point."""
    series_ref = _SeriesRef(series)

    def interpolate(ctx: "Context", dt: date) -> Formula[float | None]:
        point = previous_point(ctx, series_ref.get(), dt)
        if point is None:
            return Formula.pure(None)
        return Formula(_PointValueOp(ctx, point))

    return interpolate


def accumulate(
    start: date,
    value: float | None,
    changes: SpanSeriesRef,
    label: str = "AccumulatedPointSeries",
) -> PointSeriesDef:
    """Create a point series by accumulating span changes from a start value."""
    changes_ref = _SeriesRef(changes)

    def accumulated_value(ctx: "Context", dt: date) -> Formula[float | None]:
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

    def points(ctx: "Context") -> Iterable[Point]:
        yield Point(start, Formula.pure(value))
        for span in _iter_cached_spans(ctx, changes_ref.get()):
            if span.period.end > start:
                yield Point(span.period.end, accumulated_value(ctx, span.period.end))

    return PointSeriesDef(fn=points, interpolate=accumulated_value, label=label)


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
    return _operator(
        label or f"Scale{_ref_label(series, 'PointSeries')}", [series], scale_values(factor)
    )


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
        label or f"Sub{_ref_label(left, 'LeftPointSeries')}{_ref_label(right, 'RightPointSeries')}",
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
        label or f"Div{_ref_label(left, 'LeftPointSeries')}{_ref_label(right, 'RightPointSeries')}",
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


def align_points(
    ctx: "Context",
    series: Sequence[PointSeriesDef],
) -> Iterator[tuple[Point, ...]]:
    """Yield point tuples across series over their source dates."""
    if not series:
        return

    caches = [ctx.get_or_create_point_cache(s) for s in series]
    cursor: date | None = None

    while True:
        for cache in caches:
            if cursor is None:
                cache.ensure_materialized_at_or_after(date.min)
            else:
                cache.ensure_materialized_after(cursor)

        dates = [
            point.dt
            for cache in caches
            for point in cache.source_points.values()
            if cursor is None or point.dt > cursor
        ]
        if not dates:
            return

        cursor = min(dates)
        yield tuple(point_series.query(ctx, cursor) for point_series in series)


def _operator(
    label: str,
    series_defs: Sequence[PointSeriesRef],
    op: ValueOp,
) -> PointSeriesDef:
    series_refs = tuple(_SeriesRef(series) for series in series_defs)

    def points(ctx: "Context") -> Iterable[Point]:
        resolved_series = [series.get() for series in series_refs]
        for aligned in align_points(ctx, resolved_series):
            dt = aligned[0].dt
            yield Point(dt, Formula(_PointTupleValueOp(ctx, aligned, op)))

    def interpolate(ctx: "Context", dt: date) -> Formula[float | None]:
        points = [series.get().query(ctx, dt) for series in series_refs]
        return Formula(_PointTupleValueOp(ctx, points, op))

    return PointSeriesDef(fn=points, interpolate=interpolate, label=label)


class _PointTupleValueOp(Op[float | None]):
    def __init__(self, ctx: "Context", points: Sequence[Point], op: ValueOp) -> None:
        self.ctx = ctx
        self.points = points
        self.op = op

    def eval(self) -> float | None:
        return self.op([point.eval(self.ctx) for point in self.points])

    def __repr__(self) -> str:
        return f"PointTupleValueOp(points={self.points!r})"
