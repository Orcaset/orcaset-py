from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Period,
    PointSeriesDef,
    Span,
    SpanSeriesDef,
    no_split,
    point,
    span,
    sum_spans,
)


def test_point_define_creates_queryable_series_def():
    @point.define(label="Daily price")
    def price(ctx: Context, dt: date) -> Formula[float | None]:
        return Formula.pure(42.0 if dt == date(2026, 1, 1) else None)

    ctx = Context()
    cell = price.query(ctx, date(2026, 1, 1))

    assert isinstance(price, PointSeriesDef)
    assert price.label == "Daily price"
    assert cell.dt == date(2026, 1, 1)
    assert cell.eval(ctx) == 42.0
    assert price.value(ctx, date(2026, 1, 2)).eval() is None
    assert price.query(ctx, date(2026, 1, 1)) is cell


def test_span_define_creates_queryable_series_def():
    @span.define(agg=sum_spans(0.0), label="Monthly revenue")
    def revenue(ctx: Context) -> Iterable[Span]:
        for period in Period.list(date(2026, 1, 1), relativedelta(months=1), date(2026, 3, 1)):
            yield Span(period, Formula.pure(100.0), no_split)

    ctx = Context()
    spans = revenue.query(ctx, Period(date(2026, 1, 1), date(2026, 3, 1))).eval()

    assert isinstance(revenue, SpanSeriesDef)
    assert revenue.label == "Monthly revenue"
    assert [span.eval(ctx) for span in spans] == [100.0, 100.0]
    assert revenue.value(ctx, Period(date(2026, 1, 1), date(2026, 3, 1))).eval() == 200.0


def test_span_can_evaluate_to_none():
    ctx = Context()
    span_cell = Span(Period(date(2026, 1, 1), date(2026, 2, 1)), Formula.pure(None), no_split)

    assert span_cell.eval(ctx) is None
