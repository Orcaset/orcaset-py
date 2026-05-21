from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Group,
    Period,
    PointSeries,
    Span,
    SpanSeries,
    Stmt,
    Total,
    fixed_width_table,
    point,
    span,
    split_daily,
    sum_spans,
)

# --------------- ASSUMPTIONS ---------------
start_date = date(2025, 12, 31)
initial_balance = 100.0
interest_rate = 0.05


# ------------------ CELLS ------------------
interest_data = [
    ((date(2025, 12, 31), date(2026, 3, 31)), 1.00),
    ((date(2026, 3, 31), date(2026, 6, 30)), 2.00),
    ((date(2026, 6, 30), date(2026, 9, 30)), 3.00),
]

historical_spans = [Span(Period(*c[0]), Formula.pure(c[1]), split_daily) for c in interest_data]


# ---------- INTEREST (SPAN SERIES) ----------
class Interest(SpanSeries):
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        s: Span | None = None
        # Yield historical interest accruals
        for s in historical_spans:
            yield s

        # Yield projected interest accruals
        if s is None:
            return

        # Initial example: grow at 5% compounding quarterly
        # for period in Period.seq(s.period.end, relativedelta(months=3, day=31)):
        #     s = Span(
        #         period=period,
        #         fn=s.fn * (1 + interest_rate / 4),
        #         split=split_daily,
        #     )
        #     yield s

        # Linked example: interest is based on the beginning period balance
        for period in Period.seq(s.period.end, relativedelta(months=3, day=31)):
            yield Span(
                period=period,
                fn=self.ctx.get(Balance).value(period.start) * interest_rate / 4,
                split=split_daily,
            )


# ----------- BALANCE (POINT SERIES) -----------
class Balance(PointSeries):
    def point(self, dt: date) -> Formula[float | None]:
        # Return None for dates before the start date
        if dt < start_date:
            return Formula.pure(None)

        # Return the initial balance for the start date
        if dt == start_date:
            return Formula.pure(initial_balance)

        # Return the initial balance plus the interest accrued to `dt`
        interest = self.ctx.get(Interest).value(Period(start_date, dt))
        return initial_balance + interest


# ------------- RESOLVING VALUES -------------
ctx = Context()

cell = historical_spans[0]
print("\nInitial interest cell value: ", cell.eval(ctx))
# Initial interest cell value:  1.0

interest = ctx.get(Interest)
balance = ctx.get(Balance)
monthly_period = relativedelta(months=1, day=31)

print("\nEnd Date\tBalance\tInterest")
for period in Period.seq(start_date, monthly_period, end=date(2026, 12, 31)):
    int_acc = interest.value(period).eval()
    bal = balance.value(period.end).eval()
    print(f"{period.end:%m/%d/%Y}\t{bal:,.2f}\t{int_acc:,.2f}")

# End Date        Balance Interest
# 01/31/2026      100.34  0.34
# 02/28/2026      100.66  0.31
# 03/31/2026      101.00  0.34
# ...

print("\n")

# ----------- SIMPLIFYING THE MODEL -----------
# Redefine Balance using the `point.accumulate` convenience constructor
Balance2 = point.accumulate(start_date, initial_balance, Interest)

# Demo other convenience constructors
OperatingIncome = span.define(
    lambda _: [
        Span(p, Formula.pure(100.0), split_daily)
        for p in Period.seq(start_date, relativedelta(years=1))
    ],
    agg=sum_spans(0.0),
)
PreTaxIncome = span.sum([OperatingIncome, Interest], agg=sum_spans(0.0))
Taxes = PreTaxIncome * -0.25
NetIncome = span.sum([PreTaxIncome, Taxes], agg=sum_spans(0.0))


# ------------- STRUCTURED OUTPUT -------------
# Add better labels to the series
NetIncome.label = "Net Income"
Taxes.label = "Taxes"
PreTaxIncome.label = "Pre-Tax Income"
OperatingIncome.label = "Operating Income"


# Create statement
stmt = Stmt(
    Group([Total(NetIncome, [Total(PreTaxIncome, [OperatingIncome, Interest]), Taxes])]),
    Group([Balance]),
)

# Materialize values and print as a constant-width table
periods = Period.list(start_date, relativedelta(years=1), date(2030, 12, 31))
results = stmt.values(ctx, periods)
formatted_table = fixed_width_table(results)
print(formatted_table)

# Start                               2025-12-31  2026-12-31  2027-12-31  2028-12-31  2029-12-31
# End                     2025-12-31  2026-12-31  2027-12-31  2028-12-31  2029-12-31  2030-12-31

#       Operating Income                  100.00      100.00      100.00      100.00      100.00
#       Interest                            7.33        5.47        5.75        6.04        6.35
# ----------------------------------------------------------------------------------------------
#     Pre-Tax Income                      107.33      105.47      105.75      106.04      106.35
#     Taxes                               -26.83      -26.37      -26.44      -26.51      -26.59
# ----------------------------------------------------------------------------------------------
#   Net Income                             80.49       79.10       79.31       79.53       79.76


#   Balance                   100.00      107.33      112.79      118.54      124.58      130.92
