# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from abc import ABCMeta, abstractmethod
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
from datetime import date
from typing import TYPE_CHECKING, cast, overload

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
from .cell import Span, SpanFormulaTransform, SpanSplit, no_split
from .formula import Formula, Op
from .period import Period
from .series import Series

if TYPE_CHECKING:
    from .context import Context


type SpanAgg = Callable[[list[Span]], float | None]
type SpanFamilyResult[K: Hashable] = Mapping[K, Sequence[Span]]


class _SpanSeriesMeta(ABCMeta):
    def __neg__(cls) -> type["SpanSeries"]:
        return neg(cls)

    def __add__(cls, other: int | float, /) -> type["SpanSeries"]:
        if isinstance(other, int | float):
            return add_scalar(cls, other)
        return NotImplemented

    def __radd__(cls, other: int | float, /) -> type["SpanSeries"]:
        if isinstance(other, int | float):
            return add_scalar(cls, other)
        return NotImplemented

    def __sub__(cls, other: int | float, /) -> type["SpanSeries"]:
        if isinstance(other, int | float):
            return sub_scalar(cls, other)
        return NotImplemented

    def __rsub__(cls, other: int | float, /) -> type["SpanSeries"]:
        if isinstance(other, int | float):
            return rsub_scalar(other, cls)
        return NotImplemented

    def __mul__(cls, other: int | float, /) -> type["SpanSeries"]:
        if isinstance(other, int | float):
            return scale(cls, other)
        return NotImplemented

    def __rmul__(cls, other: int | float, /) -> type["SpanSeries"]:
        if isinstance(other, int | float):
            return scale(cls, other)
        return NotImplemented

    def __truediv__(cls, other: int | float, /) -> type["SpanSeries"]:
        if isinstance(other, int | float):
            return div_scalar(cls, other)
        return NotImplemented

    def __rtruediv__(cls, other: int | float, /) -> type["SpanSeries"]:
        if isinstance(other, int | float):
            return rdiv_scalar(other, cls)
        return NotImplemented


class SpanSeries(Series, metaclass=_SpanSeriesMeta):
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
            if not isinstance(series, SpanSeries):
                raise ValueError(
                    f"{type(self).__name__}.value expected key {key!r} to be backed by a SpanSeries"
                )
            series_type = cast(type[SpanSeries], type(series))
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


def _bind_family_span(family: SpanSeriesFamily, span: Span) -> Span:
    if span.source is None:
        span.source = family
    return _bind_span(family.ctx, span)


class SpanQueryOp(Op[list[Span]]):
    def __init__(self, series: SpanSeries, period: Period) -> None:
        self.series = series
        self.period = period

    def eval(self) -> list[Span]:
        span_cache = self.series.ctx.get_or_create_span_cache(self.series)

        # If the period is already cached, return the stable source or derived span.
        cached_span = span_cache.get_span(self.period)
        if cached_span is not None:
            return [_bind_span(self.series.ctx, cached_span)]

        span_cache.ensure_materialized_through(self.period.end)
        spans = [
            span
            for span in span_cache.source_spans.values()
            if span.period.start < self.period.end and span.period.end > self.period.start
        ]

        result: list[Span] = []
        cursor = self.period.start
        for span in spans:
            clipped = span_cache.get_or_add_derived_span(
                _clip_span(self.series.ctx, span, self.period)
            )
            if cursor < clipped.period.start:
                result.append(
                    span_cache.get_or_add_derived_span(
                        _none_span(Period(cursor, clipped.period.start), self.series)
                    )
                )
            result.append(clipped)
            cursor = clipped.period.end

        if cursor < self.period.end:
            result.append(
                span_cache.get_or_add_derived_span(
                    _none_span(Period(cursor, self.period.end), self.series)
                )
            )

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


def align_spans(series: Sequence[SpanSeries]) -> Iterator[tuple[Span, ...]]:
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

        active = [_active_span(cache.source_spans.values(), cursor) for cache in caches]
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
            _bind_span(ctx, caches[index].get_or_add_derived_span(_clip_span(ctx, span, period)))
            if span is not None
            else _bind_span(
                ctx, caches[index].get_or_add_derived_span(_none_span(period, series[index]))
            )
            for index, span in enumerate(active)
        )
        cursor = end


def _first_span_start(caches) -> date | None:
    starts = [span.period.start for cache in caches for span in cache.source_spans.values()]
    return min(starts) if starts else None


def _active_span(spans: Iterable[Span], dt: date) -> Span | None:
    return next((span for span in spans if span.period.start <= dt and span.period.end > dt), None)


def _next_span_start(caches, dt: date) -> date | None:
    starts = [
        span.period.start
        for cache in caches
        for span in cache.source_spans.values()
        if span.period.start > dt
    ]
    return min(starts) if starts else None


def _copy_split_metadata(transform: SpanFormulaTransform, span: Span) -> None:
    source_spans = getattr(transform, "_source_spans", None)
    if source_spans is not None:
        span._source_spans = source_spans


@overload
def define(
    fn: Callable[[SpanSeries], Iterable[Span]],
    /,
    *,
    agg: SpanAgg,
) -> type[SpanSeries]: ...


@overload
def define(
    *,
    agg: SpanAgg,
) -> Callable[[Callable[[SpanSeries], Iterable[Span]]], type[SpanSeries]]: ...


def define(
    fn: Callable[[SpanSeries], Iterable[Span]] | None = None,
    /,
    *,
    agg: SpanAgg,
) -> type[SpanSeries] | Callable[[Callable[[SpanSeries], Iterable[Span]]], type[SpanSeries]]:
    def create(fn: Callable[[SpanSeries], Iterable[Span]]) -> type[SpanSeries]:
        return cast(
            type[SpanSeries],
            type(
                fn.__name__,
                (SpanSeries,),
                {
                    "__module__": fn.__module__,
                    "__qualname__": fn.__qualname__,
                    "__doc__": fn.__doc__,
                    "agg": staticmethod(agg),
                    "spans": fn,
                },
            ),
        )

    if fn is None:
        return create

    return create(fn)


def _inherit_agg(series: type[SpanSeries]) -> SpanAgg:
    return series.agg


def _create_span_series(
    name: str,
    spans: Callable[[SpanSeries], Iterable[Span]],
    agg: SpanAgg,
) -> type[SpanSeries]:
    return cast(
        type[SpanSeries],
        type(
            name,
            (SpanSeries,),
            {
                "agg": staticmethod(agg),
                "spans": spans,
            },
        ),
    )


def from_list(
    values: Iterable[tuple[tuple[date, date], float | None]],
    *,
    agg: SpanAgg,
    split: SpanSplit = no_split,
    name: str = "ListSpanSeries",
) -> type[SpanSeries]:
    records = tuple(values)

    def spans(self: SpanSeries) -> Iterable[Span]:
        for (start, end), value in records:
            yield Span(Period(start, end), Formula.pure(value), split)

    return _create_span_series(name, spans, agg)


class _SpanTupleValueOp(Op[float | None]):
    def __init__(self, ctx: "Context", spans: Sequence[Span], op: ValueOp) -> None:
        self.ctx = ctx
        self.spans = spans
        self.op = op

    def eval(self) -> float | None:
        return self.op([span.eval(self.ctx) for span in self.spans])

    def __repr__(self) -> str:
        return f"SpanTupleValueOp(spans={self.spans!r})"


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


def neg(series: type[SpanSeries], *, name: str | None = None) -> type[SpanSeries]:
    return _operator(
        name or f"Neg{series.__name__}", [series], neg_values, agg=_inherit_agg(series)
    )


def scale(
    series: type[SpanSeries],
    factor: float,
    *,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(
        name or f"Scale{series.__name__}",
        [series],
        scale_values(factor),
        agg=_inherit_agg(series),
    )


def add_scalar(
    series: type[SpanSeries],
    value: int | float,
    *,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(
        name or f"Add{series.__name__}Scalar",
        [series],
        add_scalar_values(value),
        agg=_inherit_agg(series),
    )


def sum(
    series: Sequence[type[SpanSeries]],
    *,
    agg: SpanAgg,
    name: str = "SumSpanSeries",
) -> type[SpanSeries]:
    return _operator(name, series, sum_values, agg=agg)


def sub(
    left: type[SpanSeries],
    right: type[SpanSeries],
    *,
    agg: SpanAgg,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(
        name or f"Sub{left.__name__}{right.__name__}", [left, right], sub_values, agg=agg
    )


def sub_scalar(
    series: type[SpanSeries],
    value: int | float,
    *,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(
        name or f"Sub{series.__name__}Scalar",
        [series],
        sub_scalar_values(value),
        agg=_inherit_agg(series),
    )


def rsub_scalar(
    value: int | float,
    series: type[SpanSeries],
    *,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(
        name or f"RSubScalar{series.__name__}",
        [series],
        rsub_scalar_values(value),
        agg=_inherit_agg(series),
    )


def mul(
    series: Sequence[type[SpanSeries]],
    *,
    agg: SpanAgg,
    name: str = "MulSpanSeries",
) -> type[SpanSeries]:
    return _operator(name, series, mul_values, agg=agg)


def div(
    left: type[SpanSeries],
    right: type[SpanSeries],
    *,
    agg: SpanAgg,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(
        name or f"Div{left.__name__}{right.__name__}", [left, right], div_values, agg=agg
    )


def div_scalar(
    series: type[SpanSeries],
    value: int | float,
    *,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(
        name or f"Div{series.__name__}Scalar",
        [series],
        div_scalar_values(value),
        agg=_inherit_agg(series),
    )


def rdiv_scalar(
    value: int | float,
    series: type[SpanSeries],
    *,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(
        name or f"RDivScalar{series.__name__}",
        [series],
        rdiv_scalar_values(value),
        agg=_inherit_agg(series),
    )


def extend(
    base: type[SpanSeries],
) -> Callable[[Callable[[SpanSeries, date | None], Iterable[Span]]], type[SpanSeries]]:
    def decorator(
        continuation: Callable[[SpanSeries, date | None], Iterable[Span]],
    ) -> type[SpanSeries]:
        def spans(self: SpanSeries) -> Iterable[Span]:
            last_end: date | None = None

            for span in self.ctx.get(base).spans():
                last_end = span.period.end
                yield span

            yield from continuation(self, last_end)

        return cast(
            type[SpanSeries],
            type(
                continuation.__name__,
                (SpanSeries,),
                {
                    "__module__": continuation.__module__,
                    "__qualname__": continuation.__qualname__,
                    "__doc__": continuation.__doc__,
                    "agg": staticmethod(base.agg),
                    "spans": spans,
                },
            ),
        )

    return decorator


def _operator(
    name: str,
    series_types: Sequence[type[SpanSeries]],
    op: ValueOp,
    *,
    agg: SpanAgg,
) -> type[SpanSeries]:
    def spans(self: SpanSeries) -> Iterable[Span]:
        sources = [self.ctx.get(series_type) for series_type in series_types]
        for aligned in align_spans(sources):
            period = aligned[0].period
            yield Span(
                period,
                _span_tuple_formula(self.ctx, aligned, op),
                _span_tuple_split(self.ctx, aligned, op),
            )

    return _create_span_series(name, spans, agg)
