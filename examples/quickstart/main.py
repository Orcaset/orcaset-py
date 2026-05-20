from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Period,
    Span,
    SpanSeries,
    point,
    span,
    split_daily,
    sum_spans,
    PointSeries,
)
from orcaset.formula import Formula

#  Assumptions
start_date = date(2025, 12, 31)
initial_balance = 100.0
interest_rate = 0.05
period_length = relativedelta(months=1, day=31)


interest_data = [
    ((date(2025, 12, 31), date(2026, 3, 31)), 1.00),
    ((date(2026, 3, 31), date(2026, 6, 30)), 2.00),
    ((date(2026, 6, 30), date(2026, 9, 30)), 3.00),
]

# Model definitions - Manual
historical_spans = [Span(Period(*c[0]), Formula.pure(c[1]), split_daily) for c in interest_data]


class Interest(SpanSeries):
    def spans(self) -> Iterable[Span]:
        s: Span | None = None
        # Yield historical interest accruals
        for s in historical_spans:
            yield s

        # Yield projected interest accruals
        if s is None:
            return

        # Initial example: grow at 1% quarterly
        for period in Period.seq(s.period.end, relativedelta(months=3, day=31)):
            s = Span(
                period=period,
                fn=s.fn * 1.01,
                split=split_daily,
            )
            yield s

        # Linked example: interest is based on the beginnign period balance
        # for period in Period.seq(s.period.end, relativedelta(months=3, day=31)):
        #     yield Span(
        #         period=period,
        #         fn=self.ctx.get(Balance).value(period.start) * interest_rate / 4,
        #         split=split_daily,
        #     )


class Balance(PointSeries):
    def point(self, dt: date) -> Formula[float | None]:
        # Return None for dates before the start date
        if dt < start_date:
            return Formula.pure(None)

        # Return the initial balance for the start date
        if dt == start_date:
            return Formula.pure(initial_balance)

        # Return the initial balance plus the interest accrued to `dt`
        interest = self.ctx.get(Interest).query(Period(start_date, dt)).map(sum_spans(0.0))
        return initial_balance + interest


# Model definitions - Using convenience functions
Balance2 = point.accumulate(start_date, initial_balance, Interest)

# Output
ctx = Context()

cell = historical_spans[0]
print(cell.eval(ctx))


interest = ctx.get(Interest)
balance = ctx.get(Balance2)

print("End Date\tBalance\tInterest")
for period in Period.seq(start_date, period_length, end=date(2026, 12, 31)):
    int_acc = interest.query(period).map(sum_spans(0.0)).eval()
    bal = balance.value(period.end).eval()
    print(f"{period.end:%m/%d/%Y}\t{bal:,.2f}\t{int_acc:,.2f}")

# End Date        Balance Interest
# 01/31/2026      100.34  0.34
# 02/28/2026      100.66  0.31
# 03/31/2026      101.00  0.34
# ...


# Series combinators demo
OperatingIncome = span.define(
    lambda _: [
        Span(p, Formula.pure(100.0), split_daily)
        for p in Period.seq(start_date, relativedelta(years=1))
    ]
)
PreTaxIncome = OperatingIncome + Interest
Taxes = PreTaxIncome * -0.25
NetIncome = PreTaxIncome - Taxes
