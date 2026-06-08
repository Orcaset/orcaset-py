from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Formula,
    YF,
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
from .data import CashFlow
from .income import earnings_to_stockholders, income_tax_provision, net_earnings, total_revenue

c_qtr_offset = relativedelta(months=3, day=31)
c_qtr_lookback = relativedelta(months=-3, day=31)
yr_lookback = relativedelta(years=-1)

hist_cash_flow = CashFlow()


hist_depreciation = span.from_list(hist_cash_flow.depreciation, agg=sum_spans(0.0), split=no_split)


@span.extend(hist_depreciation, label="Depreciation")
def depreciation(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        growth = (
            YF.cmonthly(period.start, period.end) * Assumptions.CashFlow.depreciation_growth_rate
        )
        lookback_period = period.from_start(c_qtr_lookback)
        yield Span(period, depreciation.value(ctx, lookback_period) * (1 + growth), split_daily)


hist_deferred_income_taxes = span.from_list(
    hist_cash_flow.deferred_income_taxes, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_deferred_income_taxes, label="Deferred income taxes")
def deferred_income_taxes(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        prior_period = period.shift(yr_lookback)
        prior_yr_deferred_taxes = deferred_income_taxes.value(ctx, prior_period)
        prior_yr_income_tax_provision = income_tax_provision.value(ctx, prior_period)
        current_period_income_tax_provision = income_tax_provision.value(ctx, period)
        yield Span(
            period,
            current_period_income_tax_provision
            * (prior_yr_deferred_taxes / prior_yr_income_tax_provision),
            split_daily,
        )


sec_premium_amortization_values = [
    value for _, value in hist_cash_flow.sec_premium_amortization if value is not None
]
sec_premium_amortization_latest_values = sec_premium_amortization_values[-4:]
sec_premium_amortization_projected_value = (
    sum(sec_premium_amortization_latest_values) / len(sec_premium_amortization_latest_values)
    if sec_premium_amortization_latest_values
    else 0.0
)
hist_sec_premium_amortization = span.from_list(
    hist_cash_flow.sec_premium_amortization, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_sec_premium_amortization,
    label="Amortization of marketable security premiums",
)
def sec_premium_amortization(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(sec_premium_amortization_projected_value), split_daily)


accounts_receivable = span.from_list(
    hist_cash_flow.accounts_receivable, agg=sum_spans(0.0), split=no_split
).then(
    total_revenue.scale(Assumptions.CashFlow.accounts_receivable_margin),
    label="Accounts receivable",
)

hist_other_receivables = span.from_list(
    hist_cash_flow.other_receivables, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_other_receivables, label="Other receivables")
def other_receivables(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_other_receivables = other_receivables.value(ctx, period.shift(yr_lookback))
        prior_yr_revenue = total_revenue.value(ctx, period.shift(yr_lookback))
        current_period_revenue = total_revenue.value(ctx, period)
        yield Span(
            period,
            current_period_revenue * (prior_yr_other_receivables / prior_yr_revenue),
            split_daily,
        )


hist_inventories = span.from_list(hist_cash_flow.inventories, agg=sum_spans(0.0), split=no_split)


@span.extend(hist_inventories, label="Inventories")
def inventories(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        prior_period = period.shift(yr_lookback)
        prior_yr_inventories = inventories.value(ctx, prior_period)
        prior_yr_revenue = total_revenue.value(ctx, prior_period)
        current_period_revenue = total_revenue.value(ctx, period)
        yield Span(
            period,
            current_period_revenue * (prior_yr_inventories / prior_yr_revenue),
            split_daily,
        )


hist_prepaid_and_other_assets = span.from_list(
    hist_cash_flow.prepaid_and_other_assets, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_prepaid_and_other_assets, label="Prepaid expenses and other assets")
def prepaid_and_other_assets(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        prior_period = period.shift(yr_lookback)
        prior_yr_prepaid_and_other_assets = prepaid_and_other_assets.value(ctx, prior_period)
        prior_yr_revenue = total_revenue.value(ctx, prior_period)
        current_period_revenue = total_revenue.value(ctx, period)
        yield Span(
            period,
            current_period_revenue * (prior_yr_prepaid_and_other_assets / prior_yr_revenue),
            split_daily,
        )


hist_ap_and_accrued_liabilities = span.from_list(
    hist_cash_flow.ap_and_accrued_liabilities, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_ap_and_accrued_liabilities, label="Accounts payable and accrued liabilities")
def ap_and_accrued_liabilities(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        prior_period = period.shift(yr_lookback)
        prior_yr_ap_and_accrued_liabilities = ap_and_accrued_liabilities.value(ctx, prior_period)
        prior_yr_revenue = total_revenue.value(ctx, prior_period)
        current_period_revenue = total_revenue.value(ctx, period)
        yield Span(
            period,
            current_period_revenue * (prior_yr_ap_and_accrued_liabilities / prior_yr_revenue),
            split_daily,
        )


hist_income_taxes_payable = span.from_list(
    hist_cash_flow.income_taxes_payable, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_income_taxes_payable, label="Income taxes payable")
def income_taxes_payable(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        prior_period = period.shift(yr_lookback)
        prior_yr_income_taxes_payable = income_taxes_payable.value(ctx, prior_period)
        prior_yr_income_tax_provision = income_tax_provision.value(ctx, prior_period)
        current_period_income_tax_provision = income_tax_provision.value(ctx, period)
        yield Span(
            period,
            current_period_income_tax_provision
            * (prior_yr_income_taxes_payable / prior_yr_income_tax_provision),
            split_daily,
        )


postretirement_benefits_values = [
    value for _, value in hist_cash_flow.postretirement_benefits if value is not None
]
postretirement_benefits_latest_values = postretirement_benefits_values[-4:]
postretirement_benefits_projected_value = (
    sum(postretirement_benefits_latest_values) / len(postretirement_benefits_latest_values)
    if postretirement_benefits_latest_values
    else 0.0
)
hist_postretirement_benefits = span.from_list(
    hist_cash_flow.postretirement_benefits, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_postretirement_benefits, label="Postretirement health care benefits")
def postretirement_benefits(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(postretirement_benefits_projected_value), split_daily)


hist_deferred_comp_and_other_liabilities = span.from_list(
    hist_cash_flow.deferred_comp_and_other_liabilities, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_deferred_comp_and_other_liabilities,
    label="Deferred compensation and other liabilities",
)
def deferred_comp_and_other_liabilities(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        prior_period = period.shift(yr_lookback)
        prior_yr_deferred_comp_and_other_liabilities = deferred_comp_and_other_liabilities.value(
            ctx, prior_period
        )
        prior_yr_revenue = total_revenue.value(ctx, prior_period)
        current_period_revenue = total_revenue.value(ctx, period)
        yield Span(
            period,
            current_period_revenue
            * (prior_yr_deferred_comp_and_other_liabilities / prior_yr_revenue),
            split_daily,
        )


changes_in_operating_assets_and_liabilities = span.sum(
    [
        accounts_receivable,
        other_receivables,
        inventories,
        prepaid_and_other_assets,
        ap_and_accrued_liabilities,
        income_taxes_payable,
        postretirement_benefits,
        deferred_comp_and_other_liabilities,
    ],
    agg=sum_spans(0.0),
    label="Changes in operating assets and liabilities",
)

operating_cash_flow = span.sum(
    [
        net_earnings,
        depreciation,
        deferred_income_taxes,
        sec_premium_amortization,
        changes_in_operating_assets_and_liabilities,
    ],
    agg=sum_spans(0.0),
    label="Net cash provided by operating activities",
)

restricted_cash_change_data = [
    (period, 0.0 if value is None else value)
    for period, value in hist_cash_flow.restricted_cash_change
]
restricted_cash_change_values = [
    value for _, value in restricted_cash_change_data if value is not None
]
restricted_cash_change_latest_values = restricted_cash_change_values[-4:]
restricted_cash_change_projected_value = (
    sum(restricted_cash_change_latest_values) / len(restricted_cash_change_latest_values)
    if restricted_cash_change_latest_values
    else 0.0
)
hist_restricted_cash_change = span.from_list(
    restricted_cash_change_data, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_restricted_cash_change, label="Change in Restricted Cash")
def restricted_cash_change(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(restricted_cash_change_projected_value), split_daily)


hist_capex = span.from_list(hist_cash_flow.capex, agg=sum_spans(0.0), split=no_split)


@span.extend(hist_capex, label="Capital expenditures")
def capex(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        prior_period = period.shift(yr_lookback)
        prior_yr_capex = capex.value(ctx, prior_period)
        prior_yr_revenue = total_revenue.value(ctx, prior_period)
        current_period_revenue = total_revenue.value(ctx, period)
        yield Span(
            period,
            current_period_revenue * (prior_yr_capex / prior_yr_revenue),
            split_daily,
        )


split_dollar_life_insurance_repayment_data = [
    (period, 0.0 if value is None else value)
    for period, value in hist_cash_flow.split_dollar_life_insurance_repayment
]
split_dollar_life_insurance_repayment_values = [
    value for _, value in split_dollar_life_insurance_repayment_data if value is not None
]
split_dollar_life_insurance_repayment_latest_values = split_dollar_life_insurance_repayment_values[
    -4:
]
split_dollar_life_insurance_repayment_projected_value = (
    sum(split_dollar_life_insurance_repayment_latest_values)
    / len(split_dollar_life_insurance_repayment_latest_values)
    if split_dollar_life_insurance_repayment_latest_values
    else 0.0
)
hist_split_dollar_life_insurance_repayment = span.from_list(
    split_dollar_life_insurance_repayment_data, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_split_dollar_life_insurance_repayment,
    label="Repayment of Premiums on Split Dollar Life Insurance Policies",
)
def split_dollar_life_insurance_repayment(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            Formula.pure(split_dollar_life_insurance_repayment_projected_value),
            split_daily,
        )


trading_security_purchases_values = [
    value for _, value in hist_cash_flow.trading_security_purchases if value is not None
]
trading_security_purchases_latest_values = trading_security_purchases_values[-4:]
trading_security_purchases_projected_value = (
    sum(trading_security_purchases_latest_values) / len(trading_security_purchases_latest_values)
    if trading_security_purchases_latest_values
    else 0.0
)
hist_trading_security_purchases = span.from_list(
    hist_cash_flow.trading_security_purchases, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_trading_security_purchases,
    label="Purchases of trading securities",
)
def trading_security_purchases(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(trading_security_purchases_projected_value), split_daily)


trading_security_sales_values = [
    value for _, value in hist_cash_flow.trading_security_sales if value is not None
]
trading_security_sales_latest_values = trading_security_sales_values[-4:]
trading_security_sales_projected_value = (
    sum(trading_security_sales_latest_values) / len(trading_security_sales_latest_values)
    if trading_security_sales_latest_values
    else 0.0
)
hist_trading_security_sales = span.from_list(
    hist_cash_flow.trading_security_sales, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_trading_security_sales,
    label="Sales of trading securities",
)
def trading_security_sales(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(trading_security_sales_projected_value), split_daily)


afs_security_purchases_values = [
    value for _, value in hist_cash_flow.afs_security_purchases if value is not None
]
afs_security_purchases_latest_values = afs_security_purchases_values[-4:]
afs_security_purchases_projected_value = (
    sum(afs_security_purchases_latest_values) / len(afs_security_purchases_latest_values)
    if afs_security_purchases_latest_values
    else 0.0
)
hist_afs_security_purchases = span.from_list(
    hist_cash_flow.afs_security_purchases, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_afs_security_purchases,
    label="Purchase of available for sale securities",
)
def afs_security_purchases(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(afs_security_purchases_projected_value), split_daily)


afs_security_sales_maturities_values = [
    value for _, value in hist_cash_flow.afs_security_sales_maturities if value is not None
]
afs_security_sales_maturities_latest_values = afs_security_sales_maturities_values[-4:]
afs_security_sales_maturities_projected_value = (
    sum(afs_security_sales_maturities_latest_values)
    / len(afs_security_sales_maturities_latest_values)
    if afs_security_sales_maturities_latest_values
    else 0.0
)
hist_afs_security_sales_maturities = span.from_list(
    hist_cash_flow.afs_security_sales_maturities, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_afs_security_sales_maturities,
    label="Sale and maturity of available for sale securities",
)
def afs_security_sales_maturities(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            Formula.pure(afs_security_sales_maturities_projected_value),
            split_daily,
        )


investing_cash_flow = span.sum(
    [
        restricted_cash_change,
        capex,
        split_dollar_life_insurance_repayment,
        trading_security_purchases,
        trading_security_sales,
        afs_security_purchases,
        afs_security_sales_maturities,
    ],
    agg=sum_spans(0.0),
    label="Net cash provided by investing activities",
)

share_repurchases_data = [
    (period, 0.0 if value is None else value) for period, value in hist_cash_flow.share_repurchases
]
share_repurchases_values = [value for _, value in share_repurchases_data if value is not None]
share_repurchases_latest_values = share_repurchases_values[-4:]
share_repurchases_projected_value = (
    sum(share_repurchases_latest_values) / len(share_repurchases_latest_values)
    if share_repurchases_latest_values
    else 0.0
)
hist_share_repurchases = span.from_list(share_repurchases_data, agg=sum_spans(0.0), split=no_split)


@span.extend(
    hist_share_repurchases,
    label="Shares purchased and retired",
)
def share_repurchases(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(share_repurchases_projected_value), split_daily)


hist_dividends_paid = span.from_list(
    hist_cash_flow.dividends_paid, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_dividends_paid, label="Dividends paid in cash")
def dividends_paid(ctx: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        prior_period = period.shift(yr_lookback)
        prior_yr_dividends = dividends_paid.value(ctx, prior_period)
        prior_yr_earnings = earnings_to_stockholders.value(ctx, prior_period)
        current_period_earnings = earnings_to_stockholders.value(ctx, period)
        yield Span(
            period,
            current_period_earnings * (prior_yr_dividends / prior_yr_earnings),
            split_daily,
        )


bank_loan_proceeds_values = [
    value for _, value in hist_cash_flow.bank_loan_proceeds if value is not None
]
bank_loan_proceeds_latest_values = bank_loan_proceeds_values[-4:]
bank_loan_proceeds_projected_value = (
    sum(bank_loan_proceeds_latest_values) / len(bank_loan_proceeds_latest_values)
    if bank_loan_proceeds_latest_values
    else 0.0
)
hist_bank_loan_proceeds = span.from_list(
    hist_cash_flow.bank_loan_proceeds, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_bank_loan_proceeds,
    label="Proceeds from bank loans",
)
def bank_loan_proceeds(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(bank_loan_proceeds_projected_value), split_daily)


bank_loan_repayments_values = [
    value for _, value in hist_cash_flow.bank_loan_repayments if value is not None
]
bank_loan_repayments_latest_values = bank_loan_repayments_values[-4:]
bank_loan_repayments_projected_value = (
    sum(bank_loan_repayments_latest_values) / len(bank_loan_repayments_latest_values)
    if bank_loan_repayments_latest_values
    else 0.0
)
hist_bank_loan_repayments = span.from_list(
    hist_cash_flow.bank_loan_repayments, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_bank_loan_repayments,
    label="Repayment of bank loans",
)
def bank_loan_repayments(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(bank_loan_repayments_projected_value), split_daily)


financing_cash_flow = span.sum(
    [share_repurchases, dividends_paid, bank_loan_proceeds, bank_loan_repayments],
    agg=sum_spans(0.0),
    label="Net cash provided by financing activities",
)

fx_effect_on_cash_values = [
    value for _, value in hist_cash_flow.fx_effect_on_cash if value is not None
]
fx_effect_on_cash_latest_values = fx_effect_on_cash_values[-4:]
fx_effect_on_cash_projected_value = (
    sum(fx_effect_on_cash_latest_values) / len(fx_effect_on_cash_latest_values)
    if fx_effect_on_cash_latest_values
    else 0.0
)
hist_fx_effect_on_cash = span.from_list(
    hist_cash_flow.fx_effect_on_cash, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_fx_effect_on_cash,
    label="Effect of exchange rate changes on cash",
)
def fx_effect_on_cash(_: Context, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(fx_effect_on_cash_projected_value), split_daily)


cash_change = span.sum(
    [operating_cash_flow, investing_cash_flow, financing_cash_flow, fx_effect_on_cash],
    agg=sum_spans(0.0),
    label="Decrease in cash and cash equivalents",
)

cf_stmt = Group(
    [
        Total(
            operating_cash_flow,
            [
                net_earnings,
                depreciation,
                deferred_income_taxes,
                sec_premium_amortization,
                Total(
                    changes_in_operating_assets_and_liabilities,
                    [
                        accounts_receivable,
                        other_receivables,
                        inventories,
                        prepaid_and_other_assets,
                        ap_and_accrued_liabilities,
                        income_taxes_payable,
                        postretirement_benefits,
                        deferred_comp_and_other_liabilities,
                    ],
                ),
            ],
        ),
        Total(
            investing_cash_flow,
            [
                restricted_cash_change,
                capex,
                split_dollar_life_insurance_repayment,
                trading_security_purchases,
                trading_security_sales,
                afs_security_purchases,
                afs_security_sales_maturities,
            ],
        ),
        Total(
            financing_cash_flow,
            [
                share_repurchases,
                dividends_paid,
                bank_loan_proceeds,
                bank_loan_repayments,
            ],
        ),
        Total(
            cash_change,
            [
                operating_cash_flow,
                investing_cash_flow,
                financing_cash_flow,
                fx_effect_on_cash,
            ],
        ),
    ]
)
