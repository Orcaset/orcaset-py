# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from collections.abc import Callable, Iterable, Sequence
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
from .series import SpanAgg, SpanSeries, _split_span, align_spans

if TYPE_CHECKING:
    from .context import Context


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
