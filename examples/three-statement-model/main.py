from __future__ import annotations

from collections.abc import Iterable
from datetime import date

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
class Revenue(SpanSeries):
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        value = initial_revenue
        periods = Period.seq(model_start, month)

        yield Span(next(periods), Formula.pure(value), split_daily)
        for period in periods:
            value *= 1 + revenue_growth_rate * (period.end - period.start).days / 360
            yield Span(period, Formula.pure(value), split_daily)


CostOfRevenue = span.scale(Revenue, cost_of_revenue_margin, name="Cost of revenue")
GrossProfit = span.sum([Revenue, CostOfRevenue], agg=sum_spans(0.0), name="Gross profit")


OperatingExpenses = span.periodic(
    model_start,
    month,
    operating_expenses,
    agg=sum_spans(0.0),
    split=split_daily,
    name="Operating expenses",
)


class Depreciation(SpanSeries):
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        for period in Period.seq(model_start, month):
            beginning_ppe = self.ctx.get(PpeNet).value(period.start)
            yield Span(period, beginning_ppe * depreciation_rate, split_daily)


EBIT = span.sum(
    [GrossProfit, OperatingExpenses, Depreciation],
    agg=sum_spans(0.0),
    name="EBIT",
)

IncomeTax = span.scale(EBIT, income_tax_rate, name="Income tax")

NetIncome = span.sum([EBIT, IncomeTax], agg=sum_spans(0.0), name="Net income")


# ---------- CASH FLOW STATEMENT ----------
DepreciationAddBack = span.scale(Depreciation, -1, name="Depreciation add back")

OperatingCashFlow = span.sum(
    [NetIncome, DepreciationAddBack],
    agg=sum_spans(0.0),
    name="Operating cash flow",
)

CapitalExpenditures = span.scale(Revenue, capex_margin, name="Capital expenditures")


CashFlowFromFinancing = span.periodic(
    model_start,
    month,
    0.0,
    agg=sum_spans(0.0),
    split=split_daily,
    name="Cash flow from financing",
)


TotalCashFlow = span.sum(
    [OperatingCashFlow, CapitalExpenditures, CashFlowFromFinancing],
    agg=sum_spans(0.0),
    name="Total cash flow",
)


# --------------- BALANCE SHEET ---------------
Cash = point.accumulate(model_start, initial_cash, TotalCashFlow, name="Cash")

PpeAdditions = span.scale(CapitalExpenditures, -1, name="PPE additions")
PpeNetChange = span.sum(
    [PpeAdditions, Depreciation],
    agg=sum_spans(0.0),
    name="PPE net change",
)

PpeNet = point.accumulate(model_start, initial_ppe_net, PpeNetChange, name="PPE net")

TotalAssets = point.sum([Cash, PpeNet], name="Total assets")


class CommonStock(PointSeries):
    label = "Common stock"

    def point(self, dt: date) -> Formula[float | None]:
        if dt < model_start:
            return Formula.pure(None)
        return Formula.pure(common_stock_value)


RetainedEarnings = point.accumulate(
    model_start,
    initial_retained_earnings,
    NetIncome,
    name="Retained earnings",
)

TotalEquityAndLiabilities = point.sum(
    [CommonStock, RetainedEarnings],
    name="Total equity and liabilities",
)

BalanceSheetCheck = point.sub(
    TotalAssets,
    TotalEquityAndLiabilities,
    name="Balance sheet check",
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
