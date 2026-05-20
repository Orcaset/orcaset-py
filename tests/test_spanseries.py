from typing import Iterable
from datetime import date
from dateutil.relativedelta import relativedelta

import pytest

from orcaset import (
    CellConvergenceError,
    Context,
    Formula,
    Period,
    Span,
    SpanSeries,
    SpanSplitError,
    no_split,
    split_daily,
)


def eval_spans(ctx: Context, spans: list[Span]) -> list[float | None]:
    return [span.eval(ctx) for span in spans]


def test_span_series_lookback_self_reference():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for i, period in enumerate(
                Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 3, 1))
            ):
                if i == 0:
                    yield Span(period, Formula.pure(100.0), no_split)
                else:
                    prior_spans = self.ctx.get(Revenue).query(
                        period.from_start(relativedelta(months=-1))
                    )
                    yield Span(
                        period,
                        prior_spans.map(
                            lambda spans: sum(span.eval(self.ctx) or 0.0 for span in spans) + 100.0
                        ),
                        no_split,
                    )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 3, 1)))
    assert eval_spans(ctx, spans.eval()) == [100.0, 200.0]


def test_span_series_query_before_first_span_returns_zero_padding():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for period in Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 3, 1)):
                yield Span(period, Formula.pure(100.0), no_split)

    ctx = Context()
    revenue = ctx.get(Revenue)

    spans = revenue.query(Period(date(2024, 1, 1), date(2024, 2, 1))).eval()
    assert [span.period for span in spans] == [Period(date(2024, 1, 1), date(2024, 2, 1))]
    assert eval_spans(ctx, spans) == [None]


def test_span_series_exact_query_returns_original_span_without_splitting():
    def fail_split(span: Span, dt: date):
        raise AssertionError("split should not be called")

    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            period = Period(date(2025, 1, 1), date(2025, 2, 1))
            yield Span(period, Formula.pure(100.0), fail_split)

    ctx = Context()
    revenue = ctx.get(Revenue)
    span = revenue.query(Period(date(2025, 1, 1), date(2025, 2, 1))).eval()[0]

    assert span.period == Period(date(2025, 1, 1), date(2025, 2, 1))
    assert span.eval(ctx) == 100.0


def test_span_series_partial_query_returns_clipped_prorated_span():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            period = Period(date(2025, 1, 1), date(2025, 2, 1))
            yield Span(period, Formula.pure(310.0), split_daily)

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 11), date(2025, 1, 21))).eval()

    assert [span.period for span in spans] == [Period(date(2025, 1, 11), date(2025, 1, 21))]
    assert eval_spans(ctx, spans) == pytest.approx([100.0])


def test_span_series_query_pads_gaps_with_zero_value_spans():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 2, 1)),
                Formula.pure(100.0),
                no_split,
            )
            yield Span(
                Period(date(2025, 3, 1), date(2025, 4, 1)),
                Formula.pure(300.0),
                no_split,
            )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 4, 1))).eval()

    assert [span.period for span in spans] == [
        Period(date(2025, 1, 1), date(2025, 2, 1)),
        Period(date(2025, 2, 1), date(2025, 3, 1)),
        Period(date(2025, 3, 1), date(2025, 4, 1)),
    ]
    assert eval_spans(ctx, spans) == [100.0, None, 300.0]


def test_span_series_partial_query_of_unsplittable_span_raises():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            period = Period(date(2025, 1, 1), date(2025, 2, 1))
            yield Span(period, Formula.pure(100.0), no_split)

    ctx = Context()
    revenue = ctx.get(Revenue)

    with pytest.raises(SpanSplitError):
        revenue.query(Period(date(2025, 1, 1), date(2025, 1, 15))).eval()


def test_clipped_span_depends_on_original_source_span():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            period = Period(date(2025, 1, 1), date(2025, 2, 1))
            yield Span(period, Formula.pure(310.0), split_daily)

    ctx = Context()
    revenue = ctx.get(Revenue)
    original = revenue.query(Period(date(2025, 1, 1), date(2025, 2, 1))).eval()[0]
    clipped = revenue.query(Period(date(2025, 1, 11), date(2025, 1, 21))).eval()[0]

    assert clipped.eval(ctx) == pytest.approx(100.0)
    graph = ctx.deps(clipped)
    assert original.id() in graph.nodes
    assert original.id() != clipped.id()


def test_span_series_lookahead_self_reference():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for i, period in enumerate(
                Period.seq(date(2025, 1, 1), relativedelta(months=1), end=None)
            ):
                if i >= 2:
                    yield Span(period, Formula.pure(100.0), no_split)
                else:
                    next_spans = self.ctx.get(Revenue).query(
                        period.from_end(relativedelta(months=1))
                    )
                    yield Span(
                        period,
                        next_spans.map(
                            lambda spans: sum(span.eval(self.ctx) or 0.0 for span in spans) + 100.0
                        ),
                        no_split,
                    )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 5, 1)))
    assert eval_spans(ctx, spans.eval()) == [
        300.0,
        200.0,
        100.0,
        100.0,
    ]


def test_span_series_same_period_self_reference():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for i, period in enumerate(
                Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 3, 1))
            ):
                current_period = self.ctx.get(Revenue).query(period)
                yield Span(
                    period,
                    current_period.map(
                        lambda spans: sum(span.eval(self.ctx) or 0.0 for span in spans) * 0.5 + 10
                    ),
                    no_split,
                )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 3, 1)))
    assert eval_spans(ctx, spans.eval()) == pytest.approx([20.0, 20.0])


def test_span_series_same_period_non_convergence():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for period in Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 2, 1)):
                current_period = self.ctx.get(Revenue).query(period)
                yield Span(
                    period,
                    current_period.map(
                        lambda spans: sum(span.eval(self.ctx) or 0.0 for span in spans) + 1
                    ),
                    no_split,
                )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 2, 1))).eval()

    with pytest.raises(CellConvergenceError):
        ctx.solve_cells(spans, max_iterations=3)


def test_span_series_hidden_dynamic_dependency():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for i, period in enumerate(
                Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 3, 1))
            ):
                if i == 0:
                    yield Span(period, Formula.pure(100.0), no_split)
                else:
                    prior_spans = self.ctx.get(Revenue).query(
                        period.from_start(relativedelta(months=-1))
                    )

                    def read_first(spans: list[Span]) -> float:
                        span = next(iter(spans))
                        return span.eval(self.ctx) or 0.0

                    yield Span(
                        period,
                        prior_spans.map(lambda spans: read_first(spans) + 50.0),
                        no_split,
                    )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 3, 1))).eval()

    assert eval_spans(ctx, spans) == [100.0, 150.0]
    assert spans[0].id() in ctx._cell_dependencies[spans[1].id()]


def test_context_deps_returns_transitive_graph_with_resolved_values():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for i, period in enumerate(
                Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 4, 1))
            ):
                if i == 0:
                    yield Span(period, Formula.pure(100.0), no_split)
                else:
                    prior_spans = self.ctx.get(Revenue).query(
                        period.from_start(relativedelta(months=-1))
                    )
                    yield Span(
                        period,
                        prior_spans.map(
                            lambda spans: sum(span.eval(self.ctx) or 0.0 for span in spans) + 100.0
                        ),
                        no_split,
                    )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 4, 1))).eval()
    first, second, third = spans

    graph = ctx.deps(third)

    assert graph.root is third
    assert set(graph.nodes) == {first.id(), second.id(), third.id()}
    assert graph.nodes[first.id()].value == 100.0
    assert graph.nodes[second.id()].value == 200.0
    assert graph.nodes[third.id()].value == 300.0
    assert graph.nodes[first.id()].cell.source is revenue
    assert graph.nodes[second.id()].cell.source is revenue
    assert graph.nodes[third.id()].cell.source is revenue
    assert graph.edges[third.id()] == frozenset({second.id()})
    assert graph.edges[second.id()] == frozenset({first.id()})
    assert graph.edges[first.id()] == frozenset()
    assert graph.to_dot() == "\n".join(
        [
            "digraph cell_dependencies {",
            f'  cell_{first.id()} [label="cell {first.id()}\\nsource: Revenue\\nvalue: 100.0"];',
            f'  cell_{second.id()} [label="cell {second.id()}\\nsource: Revenue\\nvalue: 200.0"];',
            f'  cell_{third.id()} [label="cell {third.id()}\\nsource: Revenue\\nvalue: 300.0"];',
            f"  cell_{second.id()} -> cell_{first.id()};",
            f"  cell_{third.id()} -> cell_{second.id()};",
            "}",
        ]
    )


def test_context_deps_includes_recursive_self_edge():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for period in Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 2, 1)):
                current_period = self.ctx.get(Revenue).query(period)
                yield Span(
                    period,
                    current_period.map(
                        lambda spans: sum(span.eval(self.ctx) or 0.0 for span in spans) * 0.5 + 10
                    ),
                    no_split,
                )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 2, 1))).eval()
    span = next(iter(spans))

    graph = ctx.deps(span)

    assert graph.nodes[span.id()].value == pytest.approx(20.0)
    assert graph.edges[span.id()] == frozenset({span.id()})
    assert f"  cell_{span.id()} -> cell_{span.id()};" in graph.to_dot()
