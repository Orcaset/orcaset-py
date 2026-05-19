# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from collections.abc import Callable, Iterable, Sequence
from datetime import date
from typing import TYPE_CHECKING, cast

from ._value_ops import (
    ValueOp,
    div_values,
    mul_values,
    neg_values,
    scale_values,
    sub_values,
    sum_values,
)
from .cell import Span, SpanFormulaTransform, SpanSplit, no_split
from .formula import Formula, Op
from .period import Period
from .series import SpanSeries, _split_span, align_spans

if TYPE_CHECKING:
    from .context import Context


def define[S: SpanSeries](
    fn: Callable[[S], Iterable[Span]],
    /,
) -> type[S]:
    return cast(
        type[S],
        type(
            fn.__name__,
            (SpanSeries,),
            {
                "__module__": fn.__module__,
                "__qualname__": fn.__qualname__,
                "__doc__": fn.__doc__,
                "spans": fn,
            },
        ),
    )


def from_list(
    values: Iterable[tuple[tuple[date, date], float | None]],
    *,
    split: SpanSplit = no_split,
    name: str = "ListSpanSeries",
) -> type[SpanSeries]:
    records = tuple(values)

    def spans(self: SpanSeries) -> Iterable[Span]:
        for (start, end), value in records:
            yield Span(Period(start, end), Formula.pure(value), split)

    return type(name, (SpanSeries,), {"spans": spans})


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
    return _operator(name or f"Neg{series.__name__}", [series], neg_values)


def scale(
    series: type[SpanSeries],
    factor: float,
    *,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(name or f"Scale{series.__name__}", [series], scale_values(factor))


def sum(
    series: Sequence[type[SpanSeries]],
    *,
    name: str = "SumSpanSeries",
) -> type[SpanSeries]:
    return _operator(name, series, sum_values)


def sub(
    left: type[SpanSeries],
    right: type[SpanSeries],
    *,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(name or f"Sub{left.__name__}{right.__name__}", [left, right], sub_values)


def mul(
    series: Sequence[type[SpanSeries]],
    *,
    name: str = "MulSpanSeries",
) -> type[SpanSeries]:
    return _operator(name, series, mul_values)


def div(
    left: type[SpanSeries],
    right: type[SpanSeries],
    *,
    name: str | None = None,
) -> type[SpanSeries]:
    return _operator(name or f"Div{left.__name__}{right.__name__}", [left, right], div_values)


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

        return type(
            continuation.__name__,
            (SpanSeries,),
            {
                "__module__": continuation.__module__,
                "__qualname__": continuation.__qualname__,
                "__doc__": continuation.__doc__,
                "spans": spans,
            },
        )

    return decorator


def _operator(
    name: str,
    series_types: Sequence[type[SpanSeries]],
    op: ValueOp,
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

    return type(name, (SpanSeries,), {"spans": spans})
