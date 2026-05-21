# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

import itertools
from abc import ABC, abstractmethod
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
from datetime import date
from typing import TYPE_CHECKING, ClassVar, cast, final

from .cell import Point, Span, SpanFormulaTransform
from .formula import Formula, Op
from .period import Period

if TYPE_CHECKING:
    from .context import Context


type SpanAgg = Callable[[list[Span]], float | None]
type SpanFamilyResult[K: Hashable] = Mapping[K, Sequence[Span]]
type PointFamilyResult[K: Hashable] = Mapping[K, Point]


class Series(ABC):
    """
    The base class for all series types. Series represent (part of) a line item in a financial statement.

    Series should not be instantiated directly. Instead, use `Context.get` to create a series instance.
    """

    _ids = itertools.count()
    label: ClassVar[str | None] = None

    @final
    def __init__(self, ctx: Context):
        self._id = next(Series._ids)
        self.ctx = ctx
        self.__post_init__()

    @property
    def id(self) -> int:
        return self._id

    def __repr__(self) -> str:
        return f"Series(id={self.id})"

    @classmethod
    def display_name(cls) -> str:
        return cls.label or cls.__name__

    def __post_init__(self) -> None:
        """Post-initialization hook."""
        pass


class PointSeriesFamily[K: Hashable](Series):
    def query(self, dt: date) -> Formula[PointFamilyResult[K]]:
        return Formula(PointFamilyQueryOp(self, dt))

    def key_label(self, key: K) -> str:
        return str(key)

    @abstractmethod
    def points(self, dt: date) -> PointFamilyResult[K]:
        raise NotImplementedError


class PointSeriesBase(Series):
    def query(self, dt: date) -> Formula[Point]:
        point_cache = self.ctx.get_or_create_point_cache(self)
        if dt in point_cache:
            return Formula.pure(point_cache[dt])

        point = self.point(dt)
        point_cache[dt] = Point(dt, point, self)
        return Formula.pure(point_cache[dt])

    def value(self, dt: date) -> Formula[float | None]:
        return self.query(dt).map(lambda point: point.eval(self.ctx))

    @abstractmethod
    def point(self, dt: date) -> Formula[float | None]:
        raise NotImplementedError


class PointFamilyQueryOp[K: Hashable](Op[PointFamilyResult[K]]):
    def __init__(self, family: PointSeriesFamily[K], dt: date) -> None:
        self.family = family
        self.dt = dt

    def eval(self) -> PointFamilyResult[K]:
        result = dict(self.family.points(self.dt))
        for point in result.values():
            if point.source is None:
                point.source = self.family
        return result

    def __repr__(self) -> str:
        return f"PointFamilyQueryOp(family={self.family!r}, dt={self.dt!r})"


class SpanSeriesFamily[K: Hashable](Series):
    def query(self, period: Period) -> Formula[SpanFamilyResult[K]]:
        return Formula(SpanFamilyQueryOp(self, period))

    def value(self, period: Period) -> Formula[Mapping[K, float | None]]:
        return self.query(period).map(self._value_result)

    def key_label(self, key: K) -> str:
        return str(key)

    @abstractmethod
    def spans(self, period: Period) -> SpanFamilyResult[K]:
        raise NotImplementedError

    def _value_result(self, result: SpanFamilyResult[K]) -> Mapping[K, float | None]:
        values: dict[K, float | None] = {}
        for key, spans in result.items():
            series = self.ctx.family_series_by_key(self, key)
            if series is None:
                raise ValueError(
                    f"{type(self).__name__}.value expected a generated SpanSeries "
                    f"registered for key {key!r}"
                )
            if not isinstance(series, SpanSeriesBase):
                raise ValueError(
                    f"{type(self).__name__}.value expected key {key!r} to be backed by a SpanSeries"
                )
            series_type = cast(type[SpanSeriesBase], type(series))
            values[key] = series_type.agg(list(spans))
        return values


class SpanFamilyQueryOp[K: Hashable](Op[SpanFamilyResult[K]]):
    def __init__(self, family: SpanSeriesFamily[K], period: Period) -> None:
        self.family = family
        self.period = period

    def eval(self) -> SpanFamilyResult[K]:
        result = self.family.spans(self.period)
        return {
            key: tuple(_bind_family_span(self.family, span) for span in spans)
            for key, spans in result.items()
        }

    def __repr__(self) -> str:
        return f"SpanFamilyQueryOp(family={self.family!r}, period={self.period!r})"


class SpanQueryOp(Op[list[Span]]):
    def __init__(self, series: "SpanSeriesBase", period: Period) -> None:
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
                result.append(_none_span(Period(cursor, clipped.period.start), self.series))
            result.append(clipped)
            cursor = clipped.period.end

        if cursor < self.period.end:
            result.append(_none_span(Period(cursor, self.period.end), self.series))

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


def _bind_family_span(family: SpanSeriesFamily, span: Span) -> Span:
    if span.source is None:
        span.source = family
    return _bind_span(family.ctx, span)


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
    left = _bind_span(
        ctx,
        Span(Period(span.period.start, dt), left_fn(source), span.split, span.source),
    )
    right = _bind_span(
        ctx,
        Span(Period(dt, span.period.end), right_fn(source), span.split, span.source),
    )
    _copy_split_metadata(left_fn, left)
    _copy_split_metadata(right_fn, right)
    return left, right


def _clip_span(ctx: "Context", span: Span, period: Period) -> Span:
    if span.period.end <= period.start or span.period.start >= period.end:
        return _bind_span(ctx, _none_span(period, span.source))

    period = Period(max(span.period.start, period.start), min(span.period.end, period.end))
    _, right = _split_span(ctx, span, period.start)
    if right is None:
        raise RuntimeError("clip start removed entire span")

    left, _ = _split_span(ctx, right, period.end)
    if left is None:
        raise RuntimeError("clip end removed entire span")
    return left


def _none_span(period: Period, source: Series | None = None) -> Span:
    return Span(period, Formula.pure(None), _none_split, source)


def align_spans(series: Sequence["SpanSeriesBase"]) -> Iterator[tuple[Span, ...]]:
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
            else _bind_span(ctx, _none_span(period, series[index]))
            for index, span in enumerate(active)
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


class SpanSeriesBase(Series):
    def query(self, period: Period) -> Formula[list[Span]]:
        return Formula(SpanQueryOp(self, period))

    def value(self, period: Period) -> Formula[float | None]:
        return self.query(period).map(type(self).agg)

    @staticmethod
    @abstractmethod
    def agg(spans: list[Span]) -> float | None:
        raise NotImplementedError

    @abstractmethod
    def spans(self) -> Iterable[Span]:
        raise NotImplementedError
