from typing import Iterable
from datetime import date
from dateutil.relativedelta import relativedelta

import pytest

from orcaset import CellConvergenceError, Context, SpanSeries, Period, Span, Formula


def eval_spans(ctx: Context, spans: list[Span | None]) -> list[float | None]:
    return [span.eval(ctx) if span is not None else None for span in spans]


def test_span_series_lookback_self_reference():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for i, period in enumerate(
                Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 3, 1))
            ):
                if i == 0:
                    yield Span(period, Formula.pure(100.0))
                else:
                    prior_spans = self.ctx.get(Revenue).query(
                        period.from_start(relativedelta(months=-1))
                    )
                    yield Span(
                        period,
                        prior_spans.map(
                            lambda spans: (
                                sum(
                                    span.eval(self.ctx) or 0.0
                                    for span in spans
                                    if span is not None
                                )
                                + 100.0
                            )
                        ),
                    )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 3, 1)))
    assert eval_spans(ctx, spans.eval()) == [100.0, 200.0]


def test_span_series_lookahead_self_reference():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for i, period in enumerate(
                Period.seq(date(2025, 1, 1), relativedelta(months=1), end=None)
            ):
                if i >= 2:
                    yield Span(period, Formula.pure(100.0))
                else:
                    next_spans = self.ctx.get(Revenue).query(
                        period.from_end(relativedelta(months=1))
                    )
                    yield Span(
                        period,
                        next_spans.map(
                            lambda spans: (
                                sum(
                                    span.eval(self.ctx) or 0.0
                                    for span in spans
                                    if span is not None
                                )
                                + 100.0
                            )
                        ),
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
                        lambda spans: (
                            sum(
                                span.eval(self.ctx) or 0.0 for span in spans if span is not None
                            )
                            * 0.5
                            + 10
                        )
                    ),
                )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 3, 1)))
    assert eval_spans(ctx, spans.eval()) == pytest.approx([20.0, 20.0])


def test_span_series_same_period_non_convergence():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for period in Period.list(
                date(2025, 1, 1), relativedelta(months=1), date(2025, 2, 1)
            ):
                current_period = self.ctx.get(Revenue).query(period)
                yield Span(
                    period,
                    current_period.map(
                        lambda spans: (
                            sum(
                                span.eval(self.ctx) or 0.0 for span in spans if span is not None
                            )
                            + 1
                        )
                    ),
                )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 2, 1))).eval()

    with pytest.raises(CellConvergenceError):
        ctx.solve_cells([span for span in spans if span is not None], max_iterations=3)


def test_span_series_hidden_dynamic_dependency():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            for i, period in enumerate(
                Period.list(date(2025, 1, 1), relativedelta(months=1), date(2025, 3, 1))
            ):
                if i == 0:
                    yield Span(period, Formula.pure(100.0))
                else:
                    prior_spans = self.ctx.get(Revenue).query(
                        period.from_start(relativedelta(months=-1))
                    )

                    def read_first(spans: list[Span | None]) -> float:
                        span = next(span for span in spans if span is not None)
                        return span.eval(self.ctx) or 0.0

                    yield Span(period, prior_spans.map(lambda spans: read_first(spans) + 50.0))

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 3, 1))).eval()

    assert eval_spans(ctx, spans) == [100.0, 150.0]
    assert spans[0] is not None
    assert spans[1] is not None
    assert spans[0].id() in ctx._cell_dependencies[spans[1].id()]
