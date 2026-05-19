# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import itertools
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Sequence
from datetime import date
from typing import TYPE_CHECKING, final

from .cell import Point, Span, SpanFormulaTransform, no_split
from .formula import Formula, Op
from .period import Period

if TYPE_CHECKING:
    from .context import Context


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
    def query(self, dt: date) -> Formula[Point]:
        point_cache = self.ctx.get_or_create_point_cache(self)
        if dt in point_cache:
            return Formula.pure(point_cache[dt])

        point = self.point(dt)
        point_cache[dt] = Point(dt, point)
        return Formula.pure(point_cache[dt])

    def value(self, dt: date) -> Formula[float | None]:
        return self.query(dt).map(lambda point: point.eval(self.ctx))

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


def _copy_split_metadata(transform: SpanFormulaTransform, span: Span) -> None:
    source_spans = getattr(transform, "_source_spans", None)
    if source_spans is not None:
        span._source_spans = source_spans


class SpanSeries(Series):
    def query(self, period: Period) -> Formula[list[Span]]:
        return Formula(SpanQueryOp(self, period))

    @abstractmethod
    def spans(self) -> Iterable[Span]:
        raise NotImplementedError
