from typing import Iterable
from datetime import date
from dateutil.relativedelta import relativedelta
from orcaset import Context, SpanSeries, Period, Span, Formula


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
                                sum(span.fn.eval() for span in spans if span is not None) + 100.0
                            )
                        ),
                    )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 3, 1)))
    assert [s.fn.eval() if s is not None else None for s in spans.eval()] == [100.0, 200.0]


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
                                sum(span.fn.eval() for span in spans if span is not None) + 100.0
                            )
                        ),
                    )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 5, 1)))
    assert [s.fn.eval() if s is not None else None for s in spans.eval()] == [
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
                if i == 0:
                    yield Span(period, Formula.pure(100.0))
                else:
                    current_period = self.ctx.get(Revenue).query(period)
                    yield Span(
                        period,
                        current_period.map(
                            lambda spans: (
                                sum(span.fn.eval() for span in spans if span is not None) * 0.5 + 10
                            )
                        ),
                    )

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2025, 1, 1), date(2025, 3, 1)))
    assert [s.fn.eval() if s is not None else None for s in spans.eval()] == [20.0, 20.0]
