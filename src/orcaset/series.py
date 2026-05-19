# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import builtins
import itertools
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import date
from typing import TYPE_CHECKING, cast, final

from .cell import Point, Span, SpanFormulaTransform, no_split
from .formula import Formula, Op
from .period import Period

if TYPE_CHECKING:
    from .context import Context


type ValueOp = Callable[[Sequence[float | None]], float | None]


class Series(ABC):
    """
    The base class for all series types. Series represent (part of) a line item in a financial statement.

    Series should not be instantiated directly. Instead, use `Context.get` to create a series instance.
    """

    _ids = itertools.count()

    @final
    def __init__(self, ctx: Context):
        self._id = next(Series._ids)
        self.ctx = ctx
        self.__post_init__()

    def __repr__(self) -> str:
        return f"Series(id={self._id})"

    def __post_init__(self) -> None:
        """Post-initialization hook."""
        pass


class PointSeries(Series):
    @classmethod
    def define[S: "PointSeries"](
        cls: type[S],
        fn: Callable[[S, date], Formula[float | None]],
        /,
    ) -> type[S]:
        return cast(
            type[S],
            type(
                fn.__name__,
                (cls,),
                {
                    "__module__": fn.__module__,
                    "__qualname__": fn.__qualname__,
                    "__doc__": fn.__doc__,
                    "point": fn,
                },
            ),
        )

    @classmethod
    def neg(cls, series: type["PointSeries"]) -> type["PointSeries"]:
        return _point_operator(cls, f"Neg{series.__name__}", [series], _neg_values)

    @classmethod
    def scale(cls, series: type["PointSeries"], factor: float) -> type["PointSeries"]:
        return _point_operator(cls, f"Scale{series.__name__}", [series], _scale_values(factor))

    @classmethod
    def sum(cls, series: Sequence[type["PointSeries"]]) -> type["PointSeries"]:
        return _point_operator(cls, "SumPointSeries", series, _sum_values)

    @classmethod
    def sub(cls, left: type["PointSeries"], right: type["PointSeries"]) -> type["PointSeries"]:
        return _point_operator(
            cls, f"Sub{left.__name__}{right.__name__}", [left, right], _sub_values
        )

    @classmethod
    def mul(cls, series: Sequence[type["PointSeries"]]) -> type["PointSeries"]:
        return _point_operator(cls, "MulPointSeries", series, _mul_values)

    @classmethod
    def div(cls, left: type["PointSeries"], right: type["PointSeries"]) -> type["PointSeries"]:
        return _point_operator(
            cls, f"Div{left.__name__}{right.__name__}", [left, right], _div_values
        )

    @classmethod
    def extend(
        cls, base: type["PointSeries"], extension: type["PointSeries"]
    ) -> type["PointSeries"]:
        return _point_operator(
            cls,
            f"Extend{base.__name__}{extension.__name__}",
            [base, extension],
            _extend_values,
        )

    def query(self, dt: date) -> Formula[Point]:
        point_cache = self.ctx.get_or_create_point_cache(self)
        if dt in point_cache:
            return Formula.pure(point_cache[dt])

        point = self.point(dt)
        point_cache[dt] = Point(dt, point)
        return Formula.pure(point_cache[dt])

    @abstractmethod
    def point(self, dt: date) -> Formula[float | None]:
        raise NotImplementedError


class SpanQueryOp(Op[list[Span]]):
    def __init__(self, series: "SpanSeries", period: Period) -> None:
        self.series = series
        self.period = period

    def eval(self) -> list[Span]:
        span_cache = self.series.ctx.get_or_create_span_cache(self.series)

        # If the period is already materialized, return the span.
        if self.period in span_cache.spans:
            return [_bind_span(self.series.ctx, span_cache.spans[self.period])]

        span_cache.ensure_materialized_through(self.period.end)
        spans = [
            span
            for span in span_cache.spans.values()
            if span.period.start < self.period.end and span.period.end > self.period.start
        ]

        result: list[Span] = []
        cursor = self.period.start
        for span in spans:
            clipped = _clip_span(self.series.ctx, span, self.period)
            if cursor < clipped.period.start:
                result.append(_zero_span(Period(cursor, clipped.period.start)))
            result.append(clipped)
            cursor = clipped.period.end

        if cursor < self.period.end:
            result.append(_zero_span(Period(cursor, self.period.end)))

        return [_bind_span(self.series.ctx, span) for span in result]

    def __repr__(self) -> str:
        return f"SpanQueryOp(series={self.series!r}, period={self.period!r})"


class _SpanValueOp(Op[float | None]):
    def __init__(self, ctx: "Context", span: Span) -> None:
        self.ctx = ctx
        self.span = span

    def eval(self) -> float | None:
        return self.span.eval(self.ctx)

    def __repr__(self) -> str:
        return f"SpanValueOp(span={self.span!r})"


class _PointTupleValueOp(Op[float | None]):
    def __init__(self, ctx: "Context", points: Sequence[Point], op: ValueOp) -> None:
        self.ctx = ctx
        self.points = points
        self.op = op

    def eval(self) -> float | None:
        return self.op([point.eval(self.ctx) for point in self.points])

    def __repr__(self) -> str:
        return f"PointTupleValueOp(points={self.points!r})"


class _SpanTupleValueOp(Op[float | None]):
    def __init__(self, ctx: "Context", spans: Sequence[Span], op: ValueOp) -> None:
        self.ctx = ctx
        self.spans = spans
        self.op = op

    def eval(self) -> float | None:
        return self.op([span.eval(self.ctx) for span in self.spans])

    def __repr__(self) -> str:
        return f"SpanTupleValueOp(spans={self.spans!r})"


def _bind_span(ctx: "Context", span: Span) -> Span:
    span._ctx = ctx
    return span


def _none_split(span: Span, _: date) -> tuple[SpanFormulaTransform, SpanFormulaTransform]:
    def transform(_: Formula[float | None]) -> Formula[float | None]:
        return Formula.pure(None)

    return transform, transform


def _split_span(ctx: "Context", span: Span, dt: date) -> tuple[Span | None, Span | None]:
    if dt <= span.period.start:
        return None, _bind_span(ctx, span)
    if dt >= span.period.end:
        return _bind_span(ctx, span), None

    left_fn, right_fn = span.split(span, dt)
    source = Formula(_SpanValueOp(ctx, span))
    left = _bind_span(ctx, Span(Period(span.period.start, dt), left_fn(source), span.split))
    right = _bind_span(ctx, Span(Period(dt, span.period.end), right_fn(source), span.split))
    _copy_split_metadata(left_fn, left)
    _copy_split_metadata(right_fn, right)
    return left, right


def _clip_span(ctx: "Context", span: Span, period: Period) -> Span:
    if span.period.end <= period.start or span.period.start >= period.end:
        return _bind_span(ctx, _none_span(period))

    period = Period(max(span.period.start, period.start), min(span.period.end, period.end))
    _, right = _split_span(ctx, span, period.start)
    if right is None:
        raise RuntimeError("clip start removed entire span")

    left, _ = _split_span(ctx, right, period.end)
    if left is None:
        raise RuntimeError("clip end removed entire span")
    return left


def _none_span(period: Period) -> Span:
    return Span(period, Formula.pure(None), _none_split)


def _zero_span(period: Period) -> Span:
    return Span(period, Formula.pure(0.0), no_split)


def align_spans(series: Sequence["SpanSeries"]) -> Iterator[tuple[Span, ...]]:
    if not series:
        return

    ctx = series[0].ctx
    if any(s.ctx is not ctx for s in series):
        raise ValueError("align_spans requires all series to belong to the same Context")

    caches = [ctx.get_or_create_span_cache(s) for s in series]
    for cache in caches:
        cache.ensure_materialized_after(date.min)

    cursor = _first_span_start(caches)
    while cursor is not None:
        for cache in caches:
            cache.ensure_materialized_after(cursor)

        active = [_active_span(cache.spans.values(), cursor) for cache in caches]
        next_start = _next_span_start(caches, cursor)

        if all(span is None for span in active):
            cursor = next_start
            continue

        boundaries = [span.period.end for span in active if span is not None]
        if next_start is not None:
            boundaries.append(next_start)
        end = min(boundaries)
        period = Period(cursor, end)

        yield tuple(
            _bind_span(ctx, _clip_span(ctx, span, period))
            if span is not None
            else _bind_span(ctx, _none_span(period))
            for span in active
        )
        cursor = end


def _first_span_start(caches) -> date | None:
    starts = [span.period.start for cache in caches for span in cache.spans.values()]
    return min(starts) if starts else None


def _active_span(spans: Iterable[Span], dt: date) -> Span | None:
    return next((span for span in spans if span.period.start <= dt and span.period.end > dt), None)


def _next_span_start(caches, dt: date) -> date | None:
    starts = [
        span.period.start
        for cache in caches
        for span in cache.spans.values()
        if span.period.start > dt
    ]
    return min(starts) if starts else None


def _span_tuple_formula(
    ctx: "Context", spans: Sequence[Span], op: ValueOp
) -> Formula[float | None]:
    return Formula(_SpanTupleValueOp(ctx, spans, op))


def _span_tuple_split(
    ctx: "Context", spans: Sequence[Span], op: ValueOp
) -> Callable[[Span, date], tuple[SpanFormulaTransform, SpanFormulaTransform]]:
    def split(span: Span, dt: date) -> tuple[SpanFormulaTransform, SpanFormulaTransform]:
        source_spans = span._source_spans or spans
        left_spans: list[Span] = []
        right_spans: list[Span] = []
        for source_span in source_spans:
            left, right = _split_span(ctx, source_span, dt)
            if left is None or right is None:
                raise RuntimeError("operator split expected an interior split")
            left_spans.append(left)
            right_spans.append(right)

        def left_transform(_: Formula[float | None]) -> Formula[float | None]:
            return _span_tuple_formula(ctx, left_spans, op)

        def right_transform(_: Formula[float | None]) -> Formula[float | None]:
            return _span_tuple_formula(ctx, right_spans, op)

        setattr(left_transform, "_source_spans", tuple(left_spans))
        setattr(right_transform, "_source_spans", tuple(right_spans))
        return left_transform, right_transform

    return split


def _copy_split_metadata(transform: SpanFormulaTransform, span: Span) -> None:
    source_spans = getattr(transform, "_source_spans", None)
    if source_spans is not None:
        span._source_spans = source_spans


def _point_operator(
    base: type[PointSeries],
    name: str,
    series_types: Sequence[type[PointSeries]],
    op: ValueOp,
) -> type[PointSeries]:
    def point(self: PointSeries, dt: date) -> Formula[float | None]:
        points = [self.ctx.get(series_type).query(dt).eval() for series_type in series_types]
        return Formula(_PointTupleValueOp(self.ctx, points, op))

    return type(name, (base,), {"point": point})


def _span_operator(
    base: type["SpanSeries"],
    name: str,
    series_types: Sequence[type["SpanSeries"]],
    op: ValueOp,
) -> type["SpanSeries"]:
    def spans(self: SpanSeries) -> Iterable[Span]:
        sources = [self.ctx.get(series_type) for series_type in series_types]
        for aligned in align_spans(sources):
            period = aligned[0].period
            yield Span(
                period,
                _span_tuple_formula(self.ctx, aligned, op),
                _span_tuple_split(self.ctx, aligned, op),
            )

    return type(name, (base,), {"spans": spans})


def _none_if_any_none(values: Sequence[float | None]) -> list[float] | None:
    if any(value is None for value in values):
        return None
    return cast(list[float], list(values))


def _neg_values(values: Sequence[float | None]) -> float | None:
    resolved = _none_if_any_none(values)
    return None if resolved is None else -resolved[0]


def _scale_values(factor: float) -> ValueOp:
    def op(values: Sequence[float | None]) -> float | None:
        resolved = _none_if_any_none(values)
        return None if resolved is None else resolved[0] * factor

    return op


def _sum_values(values: Sequence[float | None]) -> float | None:
    resolved = _none_if_any_none(values)
    return None if resolved is None else builtins.sum(resolved)


def _sub_values(values: Sequence[float | None]) -> float | None:
    resolved = _none_if_any_none(values)
    return None if resolved is None else resolved[0] - resolved[1]


def _mul_values(values: Sequence[float | None]) -> float | None:
    resolved = _none_if_any_none(values)
    if resolved is None:
        return None
    product = 1.0
    for value in resolved:
        product *= value
    return product


def _div_values(values: Sequence[float | None]) -> float | None:
    resolved = _none_if_any_none(values)
    return None if resolved is None else resolved[0] / resolved[1]


def _extend_values(values: Sequence[float | None]) -> float | None:
    base, extension = values
    return extension if extension is not None else base


class SpanSeries(Series):
    @classmethod
    def define[S: "SpanSeries"](
        cls: type[S],
        fn: Callable[[S], Iterable[Span]],
        /,
    ) -> type[S]:
        return cast(
            type[S],
            type(
                fn.__name__,
                (cls,),
                {
                    "__module__": fn.__module__,
                    "__qualname__": fn.__qualname__,
                    "__doc__": fn.__doc__,
                    "spans": fn,
                },
            ),
        )

    @classmethod
    def neg(cls, series: type["SpanSeries"]) -> type["SpanSeries"]:
        return _span_operator(cls, f"Neg{series.__name__}", [series], _neg_values)

    @classmethod
    def scale(cls, series: type["SpanSeries"], factor: float) -> type["SpanSeries"]:
        return _span_operator(cls, f"Scale{series.__name__}", [series], _scale_values(factor))

    @classmethod
    def sum(cls, series: Sequence[type["SpanSeries"]]) -> type["SpanSeries"]:
        return _span_operator(cls, "SumSpanSeries", series, _sum_values)

    @classmethod
    def sub(cls, left: type["SpanSeries"], right: type["SpanSeries"]) -> type["SpanSeries"]:
        return _span_operator(
            cls, f"Sub{left.__name__}{right.__name__}", [left, right], _sub_values
        )

    @classmethod
    def mul(cls, series: Sequence[type["SpanSeries"]]) -> type["SpanSeries"]:
        return _span_operator(cls, "MulSpanSeries", series, _mul_values)

    @classmethod
    def div(cls, left: type["SpanSeries"], right: type["SpanSeries"]) -> type["SpanSeries"]:
        return _span_operator(
            cls, f"Div{left.__name__}{right.__name__}", [left, right], _div_values
        )

    @classmethod
    def extend(cls, base: type["SpanSeries"], extension: type["SpanSeries"]) -> type["SpanSeries"]:
        return _span_operator(
            cls,
            f"Extend{base.__name__}{extension.__name__}",
            [base, extension],
            _extend_values,
        )

    def query(self, period: Period) -> Formula[list[Span]]:
        return Formula(SpanQueryOp(self, period))

    @abstractmethod
    def spans(self) -> Iterable[Span]:
        raise NotImplementedError
