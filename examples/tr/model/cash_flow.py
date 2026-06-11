from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Formula,
    Context,
    Period,
    Span,
    Total,
    no_split,
    span,
    split_daily,
    sum_spans,
)

from . import dividends, ppe
from .data import CashFlow
from .income import net_earnings

c_qtr_offset = relativedelta(months=3, day=31)
yr_lookback = relativedelta(years=-1)

hist_cash_flow = CashFlow()

depreciation = ppe.depreciation


hist_deferred_income_taxes = span.from_list(
    hist_cash_flow.deferred_income_taxes, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_deferred_income_taxes, label="Deferred income taxes")
def deferred_income_taxes(ctx: Context, start: date) -> Iterable[Span]:
    from .assets import total_deferred_income_tax_assets
    from .liabilities import total_deferred_income_tax_liabilities

    for period in Period.seq(start, c_qtr_offset):
        beginning_net_deferred_tax_liability = total_deferred_income_tax_liabilities.value(
            ctx, period.start
        ) - total_deferred_income_tax_assets.value(ctx, period.start)
        ending_net_deferred_tax_liability = total_deferred_income_tax_liabilities.value(
            ctx, period.end
        ) - total_deferred_income_tax_assets.value(ctx, period.end)
        yield Span(
            period,
            ending_net_deferred_tax_liability - beginning_net_deferred_tax_liability,
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
def sec_premium_amortization(_: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(sec_premium_amortization_projected_value), split_daily)


hist_accounts_receivable = span.from_list(
    hist_cash_flow.accounts_receivable, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_accounts_receivable, label="Accounts receivable")
def accounts_receivable(ctx: Context, start: date) -> Iterable[Span]:
    from .assets import ar_trade_net

    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            ar_trade_net.value(ctx, period.start) - ar_trade_net.value(ctx, period.end),
            split_daily,
        )


hist_other_receivables = span.from_list(
    hist_cash_flow.other_receivables, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_other_receivables, label="Other receivables")
def other_receivables(ctx: Context, start: date) -> Iterable[Span]:
    from .assets import other_receivables as other_receivables_balance

    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            other_receivables_balance.value(ctx, period.start)
            - other_receivables_balance.value(ctx, period.end),
            split_daily,
        )


hist_inventories = span.from_list(hist_cash_flow.inventories, agg=sum_spans(0.0), split=no_split)


@span.extend(hist_inventories, label="Inventories")
def inventories(ctx: Context, start: date) -> Iterable[Span]:
    from .assets import finished_goods_wip, raw_materials_supplies

    for period in Period.seq(start, c_qtr_offset):
        wip_changes = finished_goods_wip.value(ctx, period.start) - finished_goods_wip.value(
            ctx, period.end
        )
        raw_materials_supplies_changes = raw_materials_supplies.value(
            ctx, period.start
        ) - raw_materials_supplies.value(ctx, period.end)
        yield Span(period, wip_changes + raw_materials_supplies_changes, split_daily)


hist_prepaid_and_other_assets = span.from_list(
    hist_cash_flow.prepaid_and_other_assets, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_prepaid_and_other_assets, label="Prepaid expenses and other assets")
def prepaid_and_other_assets(ctx: Context, start: date) -> Iterable[Span]:
    from .assets import prepaid_and_other_assets as prepaid_and_other_assets_balance
    from .assets import prepaid_expenses

    for period in Period.seq(start, c_qtr_offset):
        current_prepaids_change = prepaid_expenses.value(
            ctx, period.start
        ) - prepaid_expenses.value(ctx, period.end)
        other_assets_change = prepaid_and_other_assets_balance.value(
            ctx, period.start
        ) - prepaid_and_other_assets_balance.value(ctx, period.end)
        yield Span(
            period,
            current_prepaids_change + other_assets_change,
            split_daily,
        )


hist_ap_and_accrued_liabilities = span.from_list(
    hist_cash_flow.ap_and_accrued_liabilities, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_ap_and_accrued_liabilities, label="Accounts payable and accrued liabilities")
def ap_and_accrued_liabilities(ctx: Context, start: date) -> Iterable[Span]:
    from .liabilities import accounts_payable, accrued_liabilities

    for period in Period.seq(start, c_qtr_offset):
        accounts_payable_change = accounts_payable.value(ctx, period.end) - accounts_payable.value(
            ctx, period.start
        )
        accrued_liabilities_change = accrued_liabilities.value(
            ctx, period.end
        ) - accrued_liabilities.value(ctx, period.start)
        yield Span(
            period,
            accounts_payable_change + accrued_liabilities_change,
            split_daily,
        )


hist_income_taxes_payable = span.from_list(
    hist_cash_flow.income_taxes_payable, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_income_taxes_payable, label="Income taxes payable")
def income_taxes_payable(ctx: Context, start: date) -> Iterable[Span]:
    from .liabilities import income_taxes_payable as income_taxes_payable_balance

    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            income_taxes_payable_balance.value(ctx, period.end)
            - income_taxes_payable_balance.value(ctx, period.start),
            split_daily,
        )


hist_postretirement_benefits = span.from_list(
    hist_cash_flow.postretirement_benefits, agg=sum_spans(0.0), split=no_split
)


@span.extend(hist_postretirement_benefits, label="Postretirement health care benefits")
def postretirement_benefits(ctx: Context, start: date) -> Iterable[Span]:
    from .liabilities import postretirement_benefits as postretirement_benefits_balance

    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            postretirement_benefits_balance.value(ctx, period.end)
            - postretirement_benefits_balance.value(ctx, period.start),
            split_daily,
        )


hist_deferred_comp_and_other_liabilities = span.from_list(
    hist_cash_flow.deferred_comp_and_other_liabilities, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_deferred_comp_and_other_liabilities,
    label="Deferred compensation and other liabilities",
)
def deferred_comp_and_other_liabilities(ctx: Context, start: date) -> Iterable[Span]:
    from .liabilities import (
        deferred_comp_and_other_liabilities as deferred_comp_and_other_liabilities_balance,
    )
    from .liabilities import deferred_compensation

    for period in Period.seq(start, c_qtr_offset):
        deferred_compensation_change = deferred_compensation.value(
            ctx, period.end
        ) - deferred_compensation.value(ctx, period.start)
        deferred_comp_and_other_liabilities_change = (
            deferred_comp_and_other_liabilities_balance.value(ctx, period.end)
            - deferred_comp_and_other_liabilities_balance.value(ctx, period.start)
        )
        yield Span(
            period,
            deferred_compensation_change + deferred_comp_and_other_liabilities_change,
            split_daily,
        )


# Filed cash flow statements absorb lease balance changes in other captions, so this
# line is zero in historical periods. Projected lease balances scale with COGS from
# different starting levels, so their changes do not offset.
hist_lease_balances_net_change = span.from_list(
    [(period, 0.0) for period, _ in hist_cash_flow.deferred_income_taxes],
    agg=sum_spans(0.0),
    split=no_split,
)


@span.extend(
    hist_lease_balances_net_change,
    label="Operating lease assets and liabilities, net",
)
def lease_balances_net_change(ctx: Context, start: date) -> Iterable[Span]:
    from .assets import lease_rou_assets
    from .liabilities import lease_liabilities, lease_liabilities_noncurrent

    for period in Period.seq(start, c_qtr_offset):
        liability_change = (
            lease_liabilities.value(ctx, period.end)
            + lease_liabilities_noncurrent.value(ctx, period.end)
            - lease_liabilities.value(ctx, period.start)
            - lease_liabilities_noncurrent.value(ctx, period.start)
        )
        rou_change = lease_rou_assets.value(ctx, period.end) - lease_rou_assets.value(
            ctx, period.start
        )
        yield Span(period, liability_change - rou_change, split_daily)


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
        lease_balances_net_change,
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
def restricted_cash_change(_: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(restricted_cash_change_projected_value), split_daily)


capex = ppe.capex


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
def split_dollar_life_insurance_repayment(_: Context, start: date) -> Iterable[Span]:
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
def trading_security_purchases(_: Context, start: date) -> Iterable[Span]:
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
def trading_security_sales(_: Context, start: date) -> Iterable[Span]:
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
def afs_security_purchases(_: Context, start: date) -> Iterable[Span]:
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
def afs_security_sales_maturities(_: Context, start: date) -> Iterable[Span]:
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
hist_share_repurchases = span.from_list(share_repurchases_data, agg=sum_spans(0.0), split=no_split)


@span.extend(
    hist_share_repurchases,
    label="Shares purchased and retired",
)
def share_repurchases(_: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(0.0), split_daily)


dividends_paid = dividends.dividends_paid


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
def bank_loan_proceeds(_: Context, start: date) -> Iterable[Span]:
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
def bank_loan_repayments(_: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(bank_loan_repayments_projected_value), split_daily)


financing_cash_flow = span.sum(
    [share_repurchases, dividends_paid, bank_loan_proceeds, bank_loan_repayments],
    agg=sum_spans(0.0),
    label="Net cash provided by financing activities",
)

hist_fx_effect_on_cash = span.from_list(
    hist_cash_flow.fx_effect_on_cash, agg=sum_spans(0.0), split=no_split
)


@span.extend(
    hist_fx_effect_on_cash,
    label="Effect of exchange rate changes on cash",
)
def fx_effect_on_cash(_: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(0.0), split_daily)


cash_change = span.sum(
    [operating_cash_flow, investing_cash_flow, financing_cash_flow, fx_effect_on_cash],
    agg=sum_spans(0.0),
    label="Change in cash and cash equivalents",
)

cf_stmt = Total(
    cash_change,
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
                        lease_balances_net_change,
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
        fx_effect_on_cash,
    ],
)
