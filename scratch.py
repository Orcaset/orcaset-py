from datetime import date
from dateutil.relativedelta import relativedelta
from functools import reduce
from typing import Iterable

from orcaset import Context, Formula, Span, SpanSeries, Period, PointSeries


class Revenue(SpanSeries):
    def spans(self) -> Iterable[Span]:
        return [Span((Period(date(2025, 12, 31), date(2026, 1, 31))), Formula.pure(10.0))]


class DebtBalance(PointSeries):
    def point(self, dt: date) -> Formula[float | None]:
        queried_revenue = self.ctx.get(Revenue).query(Period(dt, dt + relativedelta(months=1)))

        def sum_revenue_values(spans: list[Span | None]) -> float | None:
            revenue_values = [span.fn for span in spans if span is not None]
            return reduce(
                lambda total, value: total.map2(value, lambda x, y: x + y),
                revenue_values,
                Formula.pure(0.0),
            ).eval()

        return queried_revenue.map(sum_revenue_values)


ctx = Context()
series = ctx.get(Revenue)
print(series.query(Period(date(2025, 1, 31), date(2026, 5, 31))))

debt_balance = ctx.get(DebtBalance)
point = debt_balance.query(date(2025, 12, 31)).eval()
print("debt balance:", point.fn.eval() if point is not None else None)

a = Formula.pure(2)
b = Formula.pure(3)
result = a.map2(b, lambda x, y: x + y)
print(result.eval())
