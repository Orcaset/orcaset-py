# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

import itertools
import builtins
from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING

from .formula import Formula
from .period import Period

if TYPE_CHECKING:
    from .context import Context
    from .series import Series


type SpanFormula = Formula[float | None]
type SpanFormulaTransform = Callable[[SpanFormula], SpanFormula]
type SpanSplit = Callable[[Span, date], tuple[SpanFormulaTransform, SpanFormulaTransform]]
type SpanAggFn = Callable[[list[Span]], float]


class SpanSplitError(RuntimeError):
    """Raised when a span must be split but cannot be meaningfully split."""


class Cell:
    _ids = itertools.count()
    fn: Formula[float | None]

    def __init__(self, source: Series | None):
        self._id = next(Cell._ids)
        self.source = source

    def id(self) -> int:
        return self._id

    def eval(self, ctx: "Context") -> float | None:
        return ctx.eval_cell(self)


class Span(Cell):
    def __init__(
        self,
        period: Period,
        fn: Formula[float | None],
        split: SpanSplit,
        source: Series | None = None,
    ):
        super().__init__(source)
        self.period = period
        self.fn = fn
        self.split = split
        self._ctx: Context | None = None
        self._source_spans: tuple[Span, ...] | None = None

    def __repr__(self) -> str:
        return f"Span(period={self.period}, fn={self.fn!r})"


def no_split(span: Span, dt: date) -> tuple[SpanFormulaTransform, SpanFormulaTransform]:
    raise SpanSplitError(f"Span {span!r} cannot be split at {dt.isoformat()}")


def split_daily(span: Span, dt: date) -> tuple[SpanFormulaTransform, SpanFormulaTransform]:
    days = (span.period.end - span.period.start).days
    left_days = (dt - span.period.start).days
    right_days = (span.period.end - dt).days

    def scale(factor: float) -> SpanFormulaTransform:
        return lambda formula: formula.map(lambda value: None if value is None else value * factor)

    return scale(left_days / days), scale(right_days / days)


def split_const(_: Span, __: date) -> tuple[SpanFormulaTransform, SpanFormulaTransform]:
    def identity(formula: SpanFormula) -> SpanFormula:
        return formula

    return identity, identity


class SpanAggregator:
    def __init__(self, fn: SpanAggFn):
        self.fn = fn

    def __call__(self, spans: list[Span]) -> float:
        return self.fn(spans)

    def __get__(self, instance: object, owner: type[object] | None = None) -> SpanAggFn:
        return self.fn


def sum_spans(fill: float) -> SpanAggregator:
    def reduce(spans: list[Span]) -> float:
        return builtins.sum(_span_value(span, fill) for span in spans)

    return SpanAggregator(reduce)


def avg_spans(yf: Callable[[date, date], float], fill: float) -> SpanAggregator:
    def reduce(spans: list[Span]) -> float:
        weighted_total = 0.0
        total_weight = 0.0
        for span in spans:
            weight = yf(span.period.start, span.period.end)
            weighted_total += _span_value(span, fill) * weight
            total_weight += weight
        return fill if total_weight == 0 else weighted_total / total_weight

    return SpanAggregator(reduce)


def _span_value(span: Span, fill: float) -> float:
    if span._ctx is None:
        raise RuntimeError("Span aggregation helpers require spans returned by SpanSeries.query")
    value = span.eval(span._ctx)
    return fill if value is None else value


class Point(Cell):
    def __init__(
        self,
        dt: date,
        fn: Formula[float | None],
        source: Series | None = None,
    ):
        super().__init__(source)
        self.dt = dt
        self.fn = fn

    def __repr__(self) -> str:
        return f"Point(dt={self.dt}, fn={self.fn!r})"
