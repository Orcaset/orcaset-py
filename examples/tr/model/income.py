from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Group,
    Period,
    Span,
    Total,
    no_split,
    span,
    split_daily,
    sum_spans,
)

from .assumptions import Assumptions
from .data import Income

c_qtr_offset = relativedelta(months=3, day=31)
yr_lookback = relativedelta(years=-1)

hist_income = Income()


hist_product_sales = span.from_list(hist_income.product_sales, agg=sum_spans(0.0), split=no_split)


@span.extend(hist_product_sales, label="Product sales")
def product_sales(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        yield Span(
            period,
            product_sales.value(ctx, prior_yr_period)
            * (1 + Assumptions.Income.product_sales_growth_rate),
            split_daily,
        )


hist_rental_revenue = span.from_list(hist_income.rental_revenue, agg=sum_spans(0.0), split=no_split)


@span.extend(hist_rental_revenue, label="Rental revenue")
def rental_revenue(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        yield Span(
            period,
            rental_revenue.value(ctx, prior_yr_period)
            * (1 + Assumptions.Income.rental_revenue_growth_rate),
            split_daily,
        )


total_revenue = span.sum([product_sales, rental_revenue], agg=sum_spans(0.0), label="Total revenue")

product_cogs = span.from_list(hist_income.product_cogs, agg=sum_spans(0.0), split=no_split).then(
    product_sales.scale(
        Assumptions.Income.product_cogs_margin,
        label="Projected product cost of goods sold",
    ),
    label="Product cost of goods sold",
)

rental_cogs = span.from_list(hist_income.rental_cogs, agg=sum_spans(0.0), split=no_split).then(
    rental_revenue.scale(
        Assumptions.Income.rental_cogs_margin,
    ),
    label="Rental cost of goods sold",
)

total_cogs = span.sum(
    [product_cogs, rental_cogs], agg=sum_spans(0.0), label="Total cost of goods sold"
)
gross_profit = span.sub(total_revenue, total_cogs, agg=sum_spans(0.0), label="Gross profit")

historical_sga = span.from_list(hist_income.sga, agg=sum_spans(0.0), split=no_split)


@span.extend(historical_sga, label="Selling, market, and administrative")
def sga(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_value = sga.value(ctx, period.shift(yr_lookback))
        yield Span(period, prior_yr_value * (1 + Assumptions.Income.sga_growth_rate), split_daily)


earnings_from_operations = span.sub(
    gross_profit, sga, agg=sum_spans(0.0), label="Earnings from operations"
)

hist_other_income = span.from_list(hist_income.other_income_net, agg=sum_spans(0.0), split=no_split)


@span.extend(hist_other_income, label="Other income, net")
def other_income(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_value = other_income.value(ctx, period.shift(yr_lookback))
        yield Span(
            period, prior_yr_value * (1 + Assumptions.Income.other_income_growth_rate), split_daily
        )


income_before_tax = span.sum(
    [earnings_from_operations, other_income], agg=sum_spans(0.0), label="Income before tax"
)

income_tax_provision = span.from_list(
    hist_income.tax_provision,
    agg=sum_spans(0.0),
    split=no_split,
    label="Income tax provision",
).then(
    income_before_tax.scale(Assumptions.Income.income_tax_rate),
    label="Income tax provision",
)

net_earnings = span.sub(
    income_before_tax, income_tax_provision, agg=sum_spans(0.0), label="Net earnings"
)


nci_net_income = span.from_list(
    hist_income.nci_net_income, agg=sum_spans(0.0), split=no_split
).then(net_earnings.scale(Assumptions.Income.nci_net_income_rate), label="NCI net income")

earnings_to_stockholders = span.sum(
    [net_earnings, nci_net_income.scale(-1.0)], agg=sum_spans(0.0), label="Earnings to stockholders"
)

# TODO: This causes division by zero error/stat
# earnings_to_stockholders = span.sub(
#     net_earnings, nci_net_income, agg=sum_spans(0.0), label="Earnings to stockholders"
# )

income_stmt = Group(
    [
        Total(
            net_earnings,
            [
                Total(
                    income_before_tax,
                    [
                        Total(
                            earnings_from_operations,
                            [
                                Total(
                                    gross_profit,
                                    [
                                        Total(total_revenue, [product_sales, rental_revenue]),
                                        Total(total_cogs, [product_cogs, rental_cogs]),
                                    ],
                                ),
                                sga,
                            ],
                        ),
                        other_income,
                    ],
                ),
                income_tax_provision,
            ],
        ),
        Group(
            [
                nci_net_income,
                earnings_to_stockholders,
            ]
        ),
    ]
)
