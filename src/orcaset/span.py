# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, NamedTuple, overload

from dateutil.relativedelta import relativedelta

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

if TYPE_CHECKING:
    from .context import Context


type SpanAgg = Callable[[list[Span]], float | None]
type SpanMapFn = Callable[[Period, Formula[float | None]], Formula[float | None]]
type SpanSeriesFn = Callable[["Context"], Iterable[Span]]
type SpanSeriesRef = SpanSeriesDef | Callable[[], SpanSeriesDef]
type SpanSeriesKeyFn[K: Hashable] = Callable[[Period], Iterable[K]]
type SpanSeriesFactory[K: Hashable] = Callable[[K], "SpanSeriesDef"]


class SpanSeriesDef(NamedTuple):
    """A period-indexed flow or level series definition."""

    fn: SpanSeriesFn
    agg: SpanAgg
    label: str

    def query(self, ctx: "Context", period: Period) -> Formula[list[Span]]:
        """Return spans covering `period`, clipping and filling gaps as needed."""
        return Formula(SpanQueryOp(ctx, self, period))

    def value(self, ctx: "Context", period: Period) -> Formula[float | None]:
        """Return a formula resolving this series value over `period`."""
        return self.query(ctx, period).map(self.agg)

    def then(
        self,
        continuation: SpanSeriesRef,
        *,
        label: str | None = None,
    ) -> SpanSeriesDef:
        """Return this series followed by `continuation` clipped to this series end."""
        return then(self, continuation, label=label)

    def clip(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        label: str | None = None,
    ) -> SpanSeriesDef:
        """Return this series clipped to an optional date window."""
        return clip(self, start=start, end=end, label=label)

    @overload
    def map(
        self,
        transform: SpanMapFn,
        /,
        *,
        label: str | None = None,
    ) -> SpanSeriesDef: ...

    @overload
    def map(
        self,
        *,
        label: str | None = None,
    ) -> Callable[[SpanMapFn], SpanSeriesDef]: ...

    def map(
        self,
        transform: SpanMapFn | None = None,
        /,
        *,
        label: str | None = None,
    ) -> SpanSeriesDef | Callable[[SpanMapFn], SpanSeriesDef]:
        """Return a mapped series, or a decorator that maps this series."""
        decorator = map(self, label=label)
        if transform is None:
            return decorator
        return decorator(transform)

    def neg(self, *, label: str | None = None) -> SpanSeriesDef:
        """Return this series with each span negated."""
        return neg(self, label=label)

    def scale(self, factor: float, *, label: str | None = None) -> SpanSeriesDef:
        """Return this series scaled by `factor`."""
        return scale(self, factor, label=label)

    def add_scalar(self, value: int | float, *, label: str | None = None) -> SpanSeriesDef:
        """Return this series with `value` added to each span."""
        return add_scalar(self, value, label=label)

    def sub_scalar(self, value: int | float, *, label: str | None = None) -> SpanSeriesDef:
        """Return this series with `value` subtracted from each span."""
        return sub_scalar(self, value, label=label)

    def rsub_scalar(self, value: int | float, *, label: str | None = None) -> SpanSeriesDef:
        """Return a series created by subtracting each span from `value`."""
        return rsub_scalar(value, self, label=label)

    def div_scalar(self, value: int | float, *, label: str | None = None) -> SpanSeriesDef:
        """Return this series with each span divided by `value`."""
        return div_scalar(self, value, label=label)

    def rdiv_scalar(self, value: int | float, *, label: str | None = None) -> SpanSeriesDef:
        """Return a series created by dividing `value` by each span."""
        return rdiv_scalar(value, self, label=label)


@dataclass(slots=True)
class KeyedSpanSeries[K: Hashable]:
    """A keyed collection of span series definitions."""

    key_fn: SpanSeriesKeyFn[K]
    series_factory: SpanSeriesFactory[K]
    label: str

    def keys(self, period: Period) -> tuple[K, ...]:
        """Return stable, de-duplicated keys for the requested period."""
        return tuple(dict.fromkeys(self.key_fn(period)))

    def get(self, ctx: "Context", key: K) -> SpanSeriesDef:
        """Return the context-cached series definition for `key`."""
        return ctx.get_or_create_keyed_span_series(self, key)

    def items(self, ctx: "Context", period: Period) -> tuple[tuple[K, SpanSeriesDef], ...]:
        """Return `(key, series)` pairs for the requested period."""
        return tuple((key, self.get(ctx, key)) for key in self.keys(period))


class SpanQueryOp(Op[list[Span]]):
    """Formula operation that evaluates a span series query."""

    def __init__(self, ctx: "Context", series: SpanSeriesDef, period: Period) -> None:
        self.ctx = ctx
        self.series = series
        self.period = period

    def eval(self) -> list[Span]:
        span_cache = self.ctx.get_or_create_span_cache(self.series)

        # If the period is already cached, return the stable source or derived span.
        cached_span = span_cache.get_span(self.period)
        if cached_span is not None:
            return [_bind_span(self.ctx, cached_span)]

        span_cache.ensure_materialized_through(self.period.end)
        spans = [
            span
            for span in span_cache.source_spans.values()
            if span.period.start < self.period.end and span.period.end > self.period.start
        ]

        result: list[Span] = []
        cursor = self.period.start
        for span in spans:
            clipped = span_cache.get_or_add_derived_span(_clip_span(self.ctx, span, self.period))
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

        return [_bind_span(self.ctx, span) for span in result]

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


def _none_span(period: Period, source: object | None = None) -> Span:
    return Span(period, Formula.pure(None), _none_split, source)


def align_spans(ctx: "Context", series: Sequence[SpanSeriesDef]) -> Iterator[tuple[Span, ...]]:
    """Yield aligned span tuples across series over their source boundaries."""
    if not series:
        return

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


def _iter_cached_spans(ctx: "Context", series: SpanSeriesDef) -> Iterator[Span]:
    cache = ctx.get_or_create_span_cache(series)
    for span in cache.iter_source_spans():
        yield _bind_span(ctx, span)


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
    fn: SpanSeriesFn,
    /,
    *,
    agg: SpanAgg,
    label: str | None = None,
) -> SpanSeriesDef: ...


@overload
def define(
    *,
    agg: SpanAgg,
    label: str | None = None,
) -> Callable[[SpanSeriesFn], SpanSeriesDef]: ...


def define(
    fn: SpanSeriesFn | None = None,
    /,
    *,
    agg: SpanAgg,
    label: str | None = None,
) -> SpanSeriesDef | Callable[[SpanSeriesFn], SpanSeriesDef]:
    """Create a span series definition from a span iterator function."""

    def create(fn: SpanSeriesFn) -> SpanSeriesDef:
        return SpanSeriesDef(fn=fn, agg=agg, label=label or fn.__name__)

    if fn is None:
        return create

    return create(fn)


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


def _ref_label(ref: SpanSeriesRef, fallback: str) -> str:
    if isinstance(ref, SpanSeriesDef):
        return ref.label
    return fallback


def _inherit_agg(series_ref: _SeriesRef[SpanSeriesDef]) -> SpanAgg:
    def agg(spans: list[Span]) -> float | None:
        return series_ref.get().agg(spans)

    return agg


def _create_span_series(
    label: str,
    spans: SpanSeriesFn,
    agg: SpanAgg,
) -> SpanSeriesDef:
    return SpanSeriesDef(fn=spans, agg=agg, label=label)


def keyed[K: Hashable](
    keys: SpanSeriesKeyFn[K],
    series: SpanSeriesFactory[K],
    *,
    label: str = "KeyedSpanSeries",
) -> KeyedSpanSeries[K]:
    """Create a keyed collection of span series definitions."""
    return KeyedSpanSeries(key_fn=keys, series_factory=series, label=label)


def from_list(
    values: Iterable[tuple[tuple[date, date], float | None]],
    *,
    agg: SpanAgg,
    split: SpanSplit = no_split,
    label: str = "ListSpanSeries",
) -> SpanSeriesDef:
    """Create a span series from explicit date-range value records."""
    records = tuple(values)

    def spans(_: "Context") -> Iterable[Span]:
        for (start, end), value in records:
            yield Span(Period(start, end), Formula.pure(value), split)

    return _create_span_series(label, spans, agg)


def constant(
    value: float | None,
    *,
    agg: SpanAgg,
    split: SpanSplit,
    start: date | None = None,
    end: date | None = None,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series with one constant span over an optional range."""
    period = Period(start or date.min, end or date.max)

    def spans(_: "Context") -> Iterable[Span]:
        yield Span(period, Formula.pure(value), split)

    return _create_span_series(label or "ConstantSpanSeries", spans, agg)


def periodic(
    start: date,
    freq: relativedelta,
    value: float | None,
    *,
    agg: SpanAgg,
    split: SpanSplit,
    end: date | None = None,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series with repeated constant spans."""

    def spans(_: "Context") -> Iterable[Span]:
        for period in Period.seq(start, freq, end):
            yield Span(period, Formula.pure(value), split)

    return _create_span_series(label or "PeriodicSpanSeries", spans, agg)


def clip(
    base: SpanSeriesRef,
    *,
    start: date | None = None,
    end: date | None = None,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series by clipping `base` to an optional date window."""
    if start is not None and end is not None and start >= end:
        raise ValueError("clip start must be before clip end")

    base_ref = _SeriesRef(base)

    def spans(ctx: "Context") -> Iterable[Span]:
        yield from _iter_clipped_spans(ctx, base_ref.get(), start=start, end=end)

    return SpanSeriesDef(
        fn=spans,
        agg=_inherit_agg(base_ref),
        label=label or f"Clip{_ref_label(base, 'SpanSeries')}",
    )


def _iter_clipped_spans(
    ctx: "Context",
    series: SpanSeriesDef,
    *,
    start: date | None = None,
    end: date | None = None,
) -> Iterator[Span]:
    for source_span in _iter_cached_spans(ctx, series):
        clipped_start = (
            max(source_span.period.start, start) if start is not None else source_span.period.start
        )
        clipped_end = (
            min(source_span.period.end, end) if end is not None else source_span.period.end
        )
        if clipped_start >= clipped_end:
            if end is not None and source_span.period.start >= end:
                break
            continue
        yield _clip_span(ctx, source_span, Period(clipped_start, clipped_end))


def then(
    base: SpanSeriesRef,
    continuation: SpanSeriesRef,
    *,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a series by appending `continuation` after `base` ends."""
    base_ref = _SeriesRef(base)
    continuation_ref = _SeriesRef(continuation)

    def spans(ctx: "Context") -> Iterable[Span]:
        last_end: date | None = None

        for base_span in _iter_cached_spans(ctx, base_ref.get()):
            last_end = base_span.period.end
            yield base_span

        yield from _iter_clipped_spans(ctx, continuation_ref.get(), start=last_end)

    return SpanSeriesDef(
        fn=spans,
        agg=_inherit_agg(base_ref),
        label=label or _ref_label(base, "ThenSpanSeries"),
    )


def map(
    base: SpanSeriesRef,
    *,
    label: str | None = None,
) -> Callable[[SpanMapFn], SpanSeriesDef]:
    """Create a decorator that maps each `base` span value and period."""
    base_ref = _SeriesRef(base)

    def decorator(transform: SpanMapFn) -> SpanSeriesDef:
        def spans(ctx: "Context") -> Iterable[Span]:
            for source_span in _iter_cached_spans(ctx, base_ref.get()):
                value = Formula(_SpanValueOp(ctx, source_span))
                yield Span(
                    source_span.period,
                    transform(source_span.period, value),
                    _map_span_split(ctx, source_span, transform),
                )

        return SpanSeriesDef(
            fn=spans,
            agg=_inherit_agg(base_ref),
            label=label or transform.__name__,
        )

    return decorator


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


def _map_span_split(
    ctx: "Context",
    source_span: Span,
    transform: SpanMapFn,
) -> Callable[[Span, date], tuple[SpanFormulaTransform, SpanFormulaTransform]]:
    def split(span: Span, dt: date) -> tuple[SpanFormulaTransform, SpanFormulaTransform]:
        (current_source,) = span._source_spans or (source_span,)
        left_source, right_source = _split_span(ctx, current_source, dt)
        if left_source is None or right_source is None:
            raise RuntimeError("map split expected an interior split")

        def transform_source(span: Span) -> Formula[float | None]:
            return transform(span.period, Formula(_SpanValueOp(ctx, span)))

        def left_transform(_: Formula[float | None]) -> Formula[float | None]:
            return transform_source(left_source)

        def right_transform(_: Formula[float | None]) -> Formula[float | None]:
            return transform_source(right_source)

        setattr(left_transform, "_source_spans", (left_source,))
        setattr(right_transform, "_source_spans", (right_source,))
        return left_transform, right_transform

    return split


def neg(series: SpanSeriesRef, *, label: str | None = None) -> SpanSeriesDef:
    """Create a span series that negates another span series."""
    series_ref = _SeriesRef(series)
    return _operator_refs(
        label or f"Neg{_ref_label(series, 'SpanSeries')}",
        [series_ref],
        neg_values,
        agg=_inherit_agg(series_ref),
    )


def scale(
    series: SpanSeriesRef,
    factor: float,
    *,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series scaled by `factor`."""
    series_ref = _SeriesRef(series)
    return _operator_refs(
        label or f"Scale{_ref_label(series, 'SpanSeries')}",
        [series_ref],
        scale_values(factor),
        agg=_inherit_agg(series_ref),
    )


def add_scalar(
    series: SpanSeriesRef,
    value: int | float,
    *,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series with `value` added to each span."""
    series_ref = _SeriesRef(series)
    return _operator_refs(
        label or f"Add{_ref_label(series, 'SpanSeries')}Scalar",
        [series_ref],
        add_scalar_values(value),
        agg=_inherit_agg(series_ref),
    )


def sum(
    series: Sequence[SpanSeriesRef],
    *,
    agg: SpanAgg,
    label: str = "SumSpanSeries",
) -> SpanSeriesDef:
    """Create a span series by summing aligned spans across series."""
    return _operator(label, series, sum_values, agg=agg)


def sub(
    left: SpanSeriesRef,
    right: SpanSeriesRef,
    *,
    agg: SpanAgg,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series that subtracts `right` from `left`."""
    return _operator(
        label or f"Sub{_ref_label(left, 'LeftSpanSeries')}{_ref_label(right, 'RightSpanSeries')}",
        [left, right],
        sub_values,
        agg=agg,
    )


def sub_scalar(
    series: SpanSeriesRef,
    value: int | float,
    *,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series with `value` subtracted from each span."""
    series_ref = _SeriesRef(series)
    return _operator_refs(
        label or f"Sub{_ref_label(series, 'SpanSeries')}Scalar",
        [series_ref],
        sub_scalar_values(value),
        agg=_inherit_agg(series_ref),
    )


def rsub_scalar(
    value: int | float,
    series: SpanSeriesRef,
    *,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series by subtracting each span from `value`."""
    series_ref = _SeriesRef(series)
    return _operator_refs(
        label or f"RSubScalar{_ref_label(series, 'SpanSeries')}",
        [series_ref],
        rsub_scalar_values(value),
        agg=_inherit_agg(series_ref),
    )


def mul(
    series: Sequence[SpanSeriesRef],
    *,
    agg: SpanAgg,
    label: str = "MulSpanSeries",
) -> SpanSeriesDef:
    """Create a span series by multiplying aligned spans across series."""
    return _operator(label, series, mul_values, agg=agg)


def div(
    left: SpanSeriesRef,
    right: SpanSeriesRef,
    *,
    agg: SpanAgg,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series that divides `left` by `right`."""
    return _operator(
        label or f"Div{_ref_label(left, 'LeftSpanSeries')}{_ref_label(right, 'RightSpanSeries')}",
        [left, right],
        div_values,
        agg=agg,
    )


def div_scalar(
    series: SpanSeriesRef,
    value: int | float,
    *,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series that divides each span by `value`."""
    series_ref = _SeriesRef(series)
    return _operator_refs(
        label or f"Div{_ref_label(series, 'SpanSeries')}Scalar",
        [series_ref],
        div_scalar_values(value),
        agg=_inherit_agg(series_ref),
    )


def rdiv_scalar(
    value: int | float,
    series: SpanSeriesRef,
    *,
    label: str | None = None,
) -> SpanSeriesDef:
    """Create a span series by dividing `value` by each span."""
    series_ref = _SeriesRef(series)
    return _operator_refs(
        label or f"RDivScalar{_ref_label(series, 'SpanSeries')}",
        [series_ref],
        rdiv_scalar_values(value),
        agg=_inherit_agg(series_ref),
    )


def extend(
    base: SpanSeriesDef,
    *,
    label: str | None = None,
) -> Callable[[Callable[["Context", date | None], Iterable[Span]]], SpanSeriesDef]:
    """Create a decorator that extends `base` with continuation spans."""

    def decorator(
        continuation: Callable[["Context", date | None], Iterable[Span]],
    ) -> SpanSeriesDef:
        def spans(ctx: "Context") -> Iterable[Span]:
            last_end: date | None = None

            for span in _iter_cached_spans(ctx, base):
                last_end = span.period.end
                yield span

            yield from continuation(ctx, last_end)

        return SpanSeriesDef(fn=spans, agg=base.agg, label=label or continuation.__name__)

    return decorator


def _operator(
    label: str,
    series_defs: Sequence[SpanSeriesRef],
    op: ValueOp,
    *,
    agg: SpanAgg,
) -> SpanSeriesDef:
    series_refs = tuple(_SeriesRef(series) for series in series_defs)
    return _operator_refs(label, series_refs, op, agg=agg)


def _operator_refs(
    label: str,
    series_refs: Sequence[_SeriesRef[SpanSeriesDef]],
    op: ValueOp,
    *,
    agg: SpanAgg,
) -> SpanSeriesDef:
    def spans(ctx: "Context") -> Iterable[Span]:
        resolved_series = [series.get() for series in series_refs]
        for aligned in align_spans(ctx, resolved_series):
            period = aligned[0].period
            yield Span(
                period,
                _span_tuple_formula(ctx, aligned, op),
                _span_tuple_split(ctx, aligned, op),
            )

    return _create_span_series(label, spans, agg)
