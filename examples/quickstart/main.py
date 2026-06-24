from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Group,
    Period,
    Point,
    Span,
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


# -------------- HISTORICAL DATA --------------
interest_data = [
    ((date(2025, 12, 31), date(2026, 3, 31)), 1.00),
    ((date(2026, 3, 31), date(2026, 6, 30)), 2.00),
    ((date(2026, 6, 30), date(2026, 9, 30)), 3.00),
]

historical_spans = [Span(Period(*c[0]), Formula.pure(c[1]), split_daily) for c in interest_data]


# ---------- INTEREST (SPAN SERIES) ----------
@span.define(agg=sum_spans(0.0), label="Interest")
def interest(ctx: Context) -> Iterable[Span]:
    s: Span | None = None
    # Yield historical interest accruals
    for s in historical_spans:
        yield s

    # Yield projected interest accruals
    if s is None:
        return

    # Non-recursive initial definition
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
            fn=balance.value(ctx, period.start) * interest_rate / 4,
            split=split_daily,
        )


# ----------- BALANCE (POINT SERIES) -----------
def balance_value(ctx: Context, dt: date) -> Formula[float | None]:
    # Return None for dates before the start date
    if dt < start_date:
        return Formula.pure(None)

    # Return the initial balance for the start date
    if dt == start_date:
        return Formula.pure(initial_balance)

    # Return the initial balance plus the interest accrued to `dt`
    interest_value = interest.value(ctx, Period(start_date, dt))
    return initial_balance + interest_value


@point.define(interpolate=balance_value, label="Balance")
def balance(_: Context) -> Iterable[Point]:
    yield Point(start_date, Formula.pure(initial_balance))


# ------------- RESOLVING VALUES -------------
ctx = Context()

cell = historical_spans[0]
print("\nInitial interest cell value: ", cell.eval(ctx))
# Initial interest cell value:  1.0

monthly_period = relativedelta(months=1, day=31)

print("\nEnd Date\tBalance\tInterest")
for period in Period.seq(start_date, monthly_period, end=date(2026, 12, 31)):
    int_acc = interest.value(ctx, period).eval()
    bal = balance.value(ctx, period.end).eval()
    print(f"{period.end:%m/%d/%Y}\t{bal:,.2f}\t{int_acc:,.2f}")

# End Date        Balance Interest
# 01/31/2026      100.34  0.34
# 02/28/2026      100.66  0.31
# 03/31/2026      101.00  0.34
# ...

print("\n")

# ----------- SIMPLIFYING THE MODEL -----------

# Create the historical interest series
historical_interest = span.from_list(
    interest_data, agg=sum_spans(0.0), split=split_daily, label="Interest 2"
)


# Extend historical interest to projections
@span.extend(historical_interest)
def interest_2(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, relativedelta(months=3, day=31)):
        yield Span(period, balance_2.value(ctx, period.start) * interest_rate / 4, split_daily)


# Redefine Balance using the `point.accumulate` convenience constructor
balance_2 = point.accumulate(start_date, initial_balance, interest_2, label="Balance 2")


# Demo other convenience constructors
@span.define(agg=sum_spans(0.0), label="Operating Income")
def operating_income(ctx: Context) -> Iterable[Span]:
    return [
        Span(p, Formula.pure(100.0), split_daily)
        for p in Period.seq(start_date, relativedelta(years=1))
    ]


pre_tax_income = span.sum([operating_income, interest], agg=sum_spans(0.0), label="Pre-Tax Income")
taxes = span.scale(pre_tax_income, -0.25, label="Taxes")
net_income = span.sum([pre_tax_income, taxes], agg=sum_spans(0.0), label="Net Income")


# Create statement
stmt = Stmt(
    Group([Total(net_income, [Total(pre_tax_income, [operating_income, interest]), taxes])]),
    Group([balance]),
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
