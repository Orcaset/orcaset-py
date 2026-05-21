from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Period,
    PointSeries,
    Span,
    SpanSeries,
    no_split,
    point,
    span,
    sum_spans,
)


def test_point_series_define_creates_queryable_series():
    @point.define
    def Price(self: PointSeries, dt: date) -> Formula[float | None]:
        """Daily price."""
        return Formula.pure(42.0 if dt == date(2026, 1, 1) else None)

    ctx = Context()
    price = ctx.get(Price)
    cell = price.query(date(2026, 1, 1)).eval()

    assert Price.__name__ == "Price"
    assert Price.__qualname__.endswith("Price")
    assert Price.__doc__ == "Daily price."
    assert issubclass(Price, PointSeries)
    assert isinstance(price, PointSeries)
    assert cell.eval(ctx) == 42.0
    assert price.query(date(2026, 1, 2)).eval().eval(ctx) is None


def test_span_series_define_creates_queryable_series():
    @span.define(agg=sum_spans(0.0))
    def Revenue(self: SpanSeries) -> Iterable[Span]:
        """Monthly revenue."""
        for period in Period.list(date(2026, 1, 1), relativedelta(months=1), date(2026, 3, 1)):
            yield Span(period, Formula.pure(100.0), no_split)

    ctx = Context()
    revenue = ctx.get(Revenue)
    spans = revenue.query(Period(date(2026, 1, 1), date(2026, 3, 1))).eval()

    assert Revenue.__name__ == "Revenue"
    assert Revenue.__qualname__.endswith("Revenue")
    assert Revenue.__doc__ == "Monthly revenue."
    assert issubclass(Revenue, SpanSeries)
    assert isinstance(revenue, SpanSeries)
    assert [span.eval(ctx) for span in spans] == [100.0, 100.0]


def test_span_can_evaluate_to_none():
    ctx = Context()
    span = Span(Period(date(2026, 1, 1), date(2026, 2, 1)), Formula.pure(None), no_split)

    assert span.eval(ctx) is None
