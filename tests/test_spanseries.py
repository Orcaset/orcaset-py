from datetime import date
from typing import Iterable

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import (
    CellConvergenceError,
    Context,
    Formula,
    Period,
    Span,
    align_spans,
    no_split,
    span,
    split_const,
    split_daily,
    sum_spans,
)


def eval_spans(ctx: Context, spans: list[Span]) -> list[float | None]:
    return [span.eval(ctx) for span in spans]


def test_span_query_clips_and_caches_partial_periods():
    revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 310.0)],
        agg=sum_spans(0.0),
        split=split_daily,
        label="Revenue",
    )

    ctx = Context()
    period = Period(date(2025, 1, 11), date(2025, 1, 21))
    first = revenue.query(ctx, period).eval()[0]
    second = revenue.query(ctx, period).eval()[0]

    assert first is second
    assert first.eval(ctx) == pytest.approx(100.0)


def test_span_query_fills_gaps_with_none_spans():
    revenue = span.from_list(
        [((date(2025, 2, 1), date(2025, 3, 1)), 200.0)],
        agg=sum_spans(0.0),
        label="Revenue",
    )

    ctx = Context()
    spans = revenue.query(ctx, Period(date(2025, 1, 1), date(2025, 3, 1))).eval()

    assert [s.period for s in spans] == [
        Period(date(2025, 1, 1), date(2025, 2, 1)),
        Period(date(2025, 2, 1), date(2025, 3, 1)),
    ]
    assert eval_spans(ctx, spans) == [None, 200.0]
    assert revenue.value(ctx, Period(date(2025, 1, 1), date(2025, 3, 1))).eval() == 200.0


def test_align_spans_uses_context_cache_and_source_boundaries():
    a = span.from_list(
        [((date(2025, 1, 1), date(2025, 3, 1)), 10.0)],
        agg=sum_spans(0.0),
        split=split_const,
        label="A",
    )
    b = span.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), 1.0),
            ((date(2025, 2, 1), date(2025, 3, 1)), 2.0),
        ],
        agg=sum_spans(0.0),
        label="B",
    )

    ctx = Context()
    aligned = list(align_spans(ctx, [a, b]))

    assert [[s.period for s in row] for row in aligned] == [
        [Period(date(2025, 1, 1), date(2025, 2, 1))] * 2,
        [Period(date(2025, 2, 1), date(2025, 3, 1))] * 2,
    ]
    assert [[s.eval(ctx) for s in row] for row in aligned] == [[10.0, 1.0], [10.0, 2.0]]


def test_span_operator_preserves_split_behavior():
    a = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 310.0)],
        agg=sum_spans(0.0),
        split=split_daily,
        label="A",
    )
    b = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 31.0)],
        agg=sum_spans(0.0),
        split=split_daily,
        label="B",
    )
    total = span.sum([a, b], agg=sum_spans(0.0), label="Total")

    ctx = Context()
    spans = total.query(ctx, Period(date(2025, 1, 11), date(2025, 1, 21))).eval()

    assert eval_spans(ctx, spans) == pytest.approx([110.0])


def test_span_series_can_self_reference_previous_periods():
    @span.define(agg=sum_spans(0.0), label="Revenue")
    def revenue(ctx: Context) -> Iterable[Span]:
        for i, period in enumerate(
            Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 4, 1))
        ):
            if i == 0:
                yield Span(period, Formula.pure(100.0), no_split)
            else:
                prior = revenue.query(ctx, period.from_start(relativedelta(months=-1)))
                yield Span(
                    period,
                    prior.map(lambda spans: sum(s.eval(ctx) or 0.0 for s in spans) + 100.0),
                    no_split,
                )

    ctx = Context()
    spans = revenue.query(ctx, Period(date(2025, 1, 1), date(2025, 4, 1))).eval()

    assert eval_spans(ctx, spans) == [100.0, 200.0, 300.0]
    graph = ctx.deps(spans[-1])
    assert graph.nodes[spans[-1].id()].value == 300.0
    assert graph.edges[spans[-1].id()] == frozenset({spans[-2].id()})
    assert f"source: {revenue.label}" in graph.to_dot()


def test_span_series_same_period_non_convergence():
    @span.define(agg=sum_spans(0.0), label="Revenue")
    def revenue(ctx: Context) -> Iterable[Span]:
        period = Period(date(2025, 1, 1), date(2025, 2, 1))
        current = revenue.query(ctx, period)
        yield Span(
            period,
            current.map(lambda spans: sum(s.eval(ctx) or 0.0 for s in spans) + 1),
            no_split,
        )

    ctx = Context()
    spans = revenue.query(ctx, Period(date(2025, 1, 1), date(2025, 2, 1))).eval()

    with pytest.raises(CellConvergenceError):
        ctx.solve_cells(spans, max_iterations=3)
