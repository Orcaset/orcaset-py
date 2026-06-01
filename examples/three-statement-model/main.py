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
operating_expenses = -200.0
depreciation_rate = -0.10 / 12
income_tax_rate = -0.20
capex_margin = -0.05

initial_cash = 1_000.0
initial_ppe_net = 10_000.0
common_stock_value = 5_000.0
initial_retained_earnings = initial_cash + initial_ppe_net - common_stock_value


# ------------- INCOME STATEMENT -------------
@span.define(agg=sum_spans(0.0), label="Revenue")
def Revenue(ctx: Context) -> Iterable[Span]:
    value = initial_revenue
    periods = Period.seq(model_start, month)

    yield Span(next(periods), Formula.pure(value), split_daily)
    for period in periods:
        value *= 1 + revenue_growth_rate * (period.end - period.start).days / 360
        yield Span(period, Formula.pure(value), split_daily)


CostOfRevenue = span.scale(Revenue, cost_of_revenue_margin, label="Cost of revenue")
GrossProfit = span.sum([Revenue, CostOfRevenue], agg=sum_spans(0.0), label="Gross profit")


OperatingExpenses = span.periodic(
    model_start,
    month,
    operating_expenses,
    agg=sum_spans(0.0),
    split=split_daily,
    label="Operating expenses",
)


@span.define(agg=sum_spans(0.0), label="Depreciation")
def Depreciation(ctx: Context) -> Iterable[Span]:
    for period in Period.seq(model_start, month):
        beginning_ppe = PpeNet.value(ctx, period.start)
        yield Span(period, beginning_ppe * depreciation_rate, split_daily)


EBIT = span.sum(
    [GrossProfit, OperatingExpenses, Depreciation],
    agg=sum_spans(0.0),
    label="EBIT",
)

IncomeTax = span.scale(EBIT, income_tax_rate, label="Income tax")

NetIncome = span.sum([EBIT, IncomeTax], agg=sum_spans(0.0), label="Net income")


# ---------- CASH FLOW STATEMENT ----------
DepreciationAddBack = span.scale(Depreciation, -1, label="Depreciation add back")

OperatingCashFlow = span.sum(
    [NetIncome, DepreciationAddBack],
    agg=sum_spans(0.0),
    label="Operating cash flow",
)

CapitalExpenditures = span.scale(Revenue, capex_margin, label="Capital expenditures")


CashFlowFromFinancing = span.periodic(
    model_start,
    month,
    0.0,
    agg=sum_spans(0.0),
    split=split_daily,
    label="Cash flow from financing",
)


TotalCashFlow = span.sum(
    [OperatingCashFlow, CapitalExpenditures, CashFlowFromFinancing],
    agg=sum_spans(0.0),
    label="Total cash flow",
)


# --------------- BALANCE SHEET ---------------
Cash = point.accumulate(model_start, initial_cash, TotalCashFlow, label="Cash")

PpeAdditions = span.scale(CapitalExpenditures, -1, label="PPE additions")
PpeNetChange = span.sum(
    [PpeAdditions, Depreciation],
    agg=sum_spans(0.0),
    label="PPE net change",
)

PpeNet = point.accumulate(model_start, initial_ppe_net, PpeNetChange, label="PPE net")

TotalAssets = point.sum([Cash, PpeNet], label="Total assets")


@point.define(label="Common stock")
def CommonStock(ctx: Context, dt: date) -> Formula[float | None]:
    if dt < model_start:
        return Formula.pure(None)
    return Formula.pure(common_stock_value)


RetainedEarnings = point.accumulate(
    model_start,
    initial_retained_earnings,
    NetIncome,
    label="Retained earnings",
)

TotalEquityAndLiabilities = point.sum(
    [CommonStock, RetainedEarnings],
    label="Total equity and liabilities",
)

BalanceSheetCheck = point.sub(
    TotalAssets,
    TotalEquityAndLiabilities,
    label="Balance sheet check",
)


# ------------- STRUCTURED OUTPUT -------------
income_stmt = Group(
    [
        Total(
            NetIncome,
            [
                Total(
                    EBIT,
                    [
                        Total(GrossProfit, [Revenue, CostOfRevenue]),
                        OperatingExpenses,
                        Depreciation,
                    ],
                ),
                IncomeTax,
            ],
        )
    ]
)

cash_flow_stmt = Group(
    [
        Total(
            TotalCashFlow,
            [
                Total(OperatingCashFlow, [NetIncome, DepreciationAddBack]),
                CapitalExpenditures,
                CashFlowFromFinancing,
            ],
        )
    ]
)

balance_sheet_stmt = Group(
    [
        Total(TotalAssets, [Cash, PpeNet]),
        Total(TotalEquityAndLiabilities, [CommonStock, RetainedEarnings]),
        BalanceSheetCheck,
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
