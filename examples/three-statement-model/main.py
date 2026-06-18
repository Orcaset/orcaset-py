from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Group,
    Period,
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
model_start = date(2025, 12, 31)
month = relativedelta(months=1, day=31)

initial_revenue = 1_000.0
revenue_growth_rate = 0.20
cost_of_revenue_margin = -0.30
operating_expenses_amount = -200.0
depreciation_rate = -0.10 / 12
income_tax_rate = -0.20
capex_margin = -0.05

initial_cash = 1_000.0
initial_ppe_net = 10_000.0
common_stock_value = 5_000.0
initial_retained_earnings = initial_cash + initial_ppe_net - common_stock_value


# ------------- INCOME STATEMENT -------------
@span.define(agg=sum_spans(0.0), label="Revenue")
def revenue(ctx: Context) -> Iterable[Span]:
    value = initial_revenue
    periods = Period.seq(model_start, month)

    yield Span(next(periods), Formula.pure(value), split_daily)
    for period in periods:
        value *= 1 + revenue_growth_rate * (period.end - period.start).days / 360
        yield Span(period, Formula.pure(value), split_daily)


cost_of_revenue = span.scale(revenue, cost_of_revenue_margin, label="Cost of revenue")
gross_profit = span.sum([revenue, cost_of_revenue], agg=sum_spans(0.0), label="Gross profit")


operating_expenses = span.periodic(
    model_start,
    month,
    operating_expenses_amount,
    agg=sum_spans(0.0),
    split=split_daily,
    label="Operating expenses",
)


@span.define(agg=sum_spans(0.0), label="Depreciation")
def depreciation(ctx: Context) -> Iterable[Span]:
    for period in Period.seq(model_start, month):
        beginning_ppe = ppe_net.value(ctx, period.start)
        yield Span(period, beginning_ppe * depreciation_rate, split_daily)


ebit = span.sum(
    [gross_profit, operating_expenses, depreciation],
    agg=sum_spans(0.0),
    label="EBIT",
)

income_tax = span.scale(ebit, income_tax_rate, label="Income tax")

net_income = span.sum([ebit, income_tax], agg=sum_spans(0.0), label="Net income")


# ---------- CASH FLOW STATEMENT ----------
depreciation_add_back = span.scale(depreciation, -1, label="Depreciation add back")

operating_cash_flow = span.sum(
    [net_income, depreciation_add_back],
    agg=sum_spans(0.0),
    label="Operating cash flow",
)

capital_expenditures = span.scale(revenue, capex_margin, label="Capital expenditures")


cash_flow_from_financing = span.periodic(
    model_start,
    month,
    0.0,
    agg=sum_spans(0.0),
    split=split_daily,
    label="Cash flow from financing",
)


total_cash_flow = span.sum(
    [operating_cash_flow, capital_expenditures, cash_flow_from_financing],
    agg=sum_spans(0.0),
    label="Total cash flow",
)


# --------------- BALANCE SHEET ---------------
cash = point.accumulate(model_start, initial_cash, total_cash_flow, label="Cash")

ppe_additions = span.scale(capital_expenditures, -1, label="PPE additions")
ppe_net_change = span.sum(
    [ppe_additions, depreciation],
    agg=sum_spans(0.0),
    label="PPE net change",
)

ppe_net = point.accumulate(model_start, initial_ppe_net, ppe_net_change, label="PPE net")

total_assets = point.sum([cash, ppe_net], label="Total assets")

common_stock = point.constant(common_stock_value, start=model_start, label="Common stock")

retained_earnings = point.accumulate(
    model_start,
    initial_retained_earnings,
    net_income,
    label="Retained earnings",
)

total_equity_and_liabilities = point.sum(
    [common_stock, retained_earnings],
    label="Total equity and liabilities",
)

balance_sheet_check = point.sub(
    total_assets,
    total_equity_and_liabilities,
    label="Balance sheet check",
)


# ------------- STRUCTURED OUTPUT -------------
income_stmt = Group(
    [
        Total(
            net_income,
            [
                Total(
                    ebit,
                    [
                        Total(gross_profit, [revenue, cost_of_revenue]),
                        operating_expenses,
                        depreciation,
                    ],
                ),
                income_tax,
            ],
        )
    ]
)

cash_flow_stmt = Group(
    [
        Total(
            total_cash_flow,
            [
                Total(operating_cash_flow, [net_income, depreciation_add_back]),
                capital_expenditures,
                cash_flow_from_financing,
            ],
        )
    ]
)

balance_sheet_stmt = Group(
    [
        Total(total_assets, [cash, ppe_net]),
        Total(total_equity_and_liabilities, [common_stock, retained_earnings]),
        balance_sheet_check,
    ]
)

stmt = Stmt(income_stmt, cash_flow_stmt, balance_sheet_stmt)


def format_value(value: float | None) -> str:
    if value is None:
        return ""
    if abs(value) < 0.005:
        value = 0.0
    return f"{value:,.2f}"


if __name__ == "__main__":
    ctx = Context()
    periods = Period.list(model_start, month, date(2026, 6, 30))
    results = stmt.values(ctx, periods)
    print(
        fixed_width_table(
            results,
            date_formatter=lambda dt: f"{dt:%Y-%m-%d}",
            value_formatter=format_value,
        )
    )
