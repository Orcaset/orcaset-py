from collections.abc import Iterable
from datetime import date
from itertools import pairwise

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Group,
    Period,
    PointSeriesDef,
    Span,
    SpanSeriesDef,
    Total,
    no_split,
    point,
    span,
    split_daily,
    sum_spans,
)

from . import cash_flow
from . import income
from . import ppe
from .data import BalanceSheet

hist_balance_sheet = BalanceSheet()
c_qtr_offset = relativedelta(months=3)
yr_lookback = relativedelta(years=-1)


def balance_changes(values: list[tuple[date, float | None]]) -> SpanSeriesDef:
    if len(values) < 2:
        raise ValueError("At least two values are required to build an accumulated series")

    changes = [
        (
            Period(prev[0], curr[0]),
            curr[1] - prev[1] if curr[1] is not None and prev[1] is not None else None,
        )
        for prev, curr in pairwise(values)
    ]
    return span.from_list(changes, agg=sum_spans(0), split=no_split)


def flat_point(values: list[tuple[date, float | None]], label: str) -> PointSeriesDef:
    @span.extend(balance_changes(values), label=f"{label} changes")
    def changes(_: Context, start: date) -> Iterable[Span]:
        for period in Period.seq(start, c_qtr_offset):
            yield Span(period, Formula.pure(0.0), split_daily)

    return point.accumulate(*values[0], changes, label=label)


deferred_income_taxes_current = point.constant(
    0.0,
    start=hist_balance_sheet.deferred_income_taxes_current[0][0],
    label="Deferred Income Taxes - Current",
)


@span.extend(balance_changes(hist_balance_sheet.cash))
def cash_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            cash_flow.cash_change.value(ctx, period)
            - cash_flow.restricted_cash_change.value(ctx, period),
            split_daily,
        )


cash = point.accumulate(*hist_balance_sheet.cash[0], cash_changes, label="Cash")


@span.extend(balance_changes(hist_balance_sheet.restricted_cash))
def restricted_cash_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, cash_flow.restricted_cash_change.value(ctx, period), split_daily)


restricted_cash = point.accumulate(
    *hist_balance_sheet.restricted_cash[0], restricted_cash_changes, label="Restricted cash"
)


@span.extend(balance_changes(hist_balance_sheet.current_investments))
def current_investments_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(0.0), split_daily)


current_investments = point.accumulate(
    *hist_balance_sheet.current_investments[0],
    current_investments_changes,
    label="Current investments",
)


@span.extend(balance_changes(hist_balance_sheet.ar_trade_net))
def ar_trade_net_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = ar_trade_net.value(ctx, prior_yr_period.end) / income.total_revenue.value(
            ctx, prior_yr_period
        )
        target_balance = prior_yr_ratio * income.total_revenue.value(ctx, period)
        yield Span(
            period,
            target_balance - ar_trade_net.value(ctx, period.start),
            split_daily,
        )


ar_trade_net = point.accumulate(
    *hist_balance_sheet.ar_trade_net[0],
    ar_trade_net_changes,
    label="Accounts receivable trade, net",
)


@span.extend(balance_changes(hist_balance_sheet.other_receivables))
def other_receivables_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = other_receivables.value(
            ctx, prior_yr_period.end
        ) / income.total_revenue.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.total_revenue.value(ctx, period)
        yield Span(
            period,
            target_balance - other_receivables.value(ctx, period.start),
            split_daily,
        )


other_receivables = point.accumulate(
    *hist_balance_sheet.other_receivables[0],
    other_receivables_changes,
    label="Other receivables",
)


@span.extend(balance_changes(hist_balance_sheet.finished_goods_wip))
def finished_goods_wip_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = finished_goods_wip.value(
            ctx, prior_yr_period.end
        ) / income.product_cogs.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.product_cogs.value(ctx, period)
        yield Span(
            period,
            target_balance - finished_goods_wip.value(ctx, period.start),
            split_daily,
        )


finished_goods_wip = point.accumulate(
    *hist_balance_sheet.finished_goods_wip[0],
    finished_goods_wip_changes,
    label="Finished goods and work-in-process",
)


@span.extend(balance_changes(hist_balance_sheet.raw_materials_supplies))
def raw_materials_supplies_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = raw_materials_supplies.value(
            ctx, prior_yr_period.end
        ) / income.product_cogs.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.product_cogs.value(ctx, period)
        yield Span(
            period,
            target_balance - raw_materials_supplies.value(ctx, period.start),
            split_daily,
        )


raw_materials_supplies = point.accumulate(
    *hist_balance_sheet.raw_materials_supplies[0],
    raw_materials_supplies_changes,
    label="Raw materials and supplies",
)


@span.extend(balance_changes(hist_balance_sheet.prepaid_expenses))
def prepaid_expenses_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = prepaid_expenses.value(
            ctx, prior_yr_period.end
        ) / income.total_revenue.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.total_revenue.value(ctx, period)
        yield Span(
            period,
            target_balance - prepaid_expenses.value(ctx, period.start),
            split_daily,
        )


prepaid_expenses = point.accumulate(
    *hist_balance_sheet.prepaid_expenses[0],
    prepaid_expenses_changes,
    label="Prepaid expenses",
)


total_current_assets = point.sum(
    [
        cash,
        restricted_cash,
        current_investments,
        ar_trade_net,
        other_receivables,
        finished_goods_wip,
        raw_materials_supplies,
        prepaid_expenses,
    ],
    label="Total current assets",
)


land = flat_point(hist_balance_sheet.land, "Land")


@span.extend(balance_changes(hist_balance_sheet.construction_in_progress))
def construction_in_progress_changes(_: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(0.0), split_daily)


construction_in_progress = point.accumulate(
    *hist_balance_sheet.construction_in_progress[0],
    construction_in_progress_changes,
    label="Construction in progress",
)


@span.extend(balance_changes(hist_balance_sheet.buildings))
def buildings_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, ppe.building_capex.value(ctx, period), split_daily)


buildings = point.accumulate(
    *hist_balance_sheet.buildings[0],
    buildings_changes,
    label="Buildings",
)


@span.extend(balance_changes(hist_balance_sheet.machinery_equipment))
def machinery_equipment_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, ppe.machinery_capex.value(ctx, period), split_daily)


machinery_equipment = point.accumulate(
    *hist_balance_sheet.machinery_equipment[0],
    machinery_equipment_changes,
    label="Machinery and equipment",
)


@span.extend(balance_changes(hist_balance_sheet.lease_rou_assets))
def lease_rou_assets_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = lease_rou_assets.value(ctx, prior_yr_period.end) / income.total_cogs.value(
            ctx, prior_yr_period
        )
        target_balance = prior_yr_ratio * income.total_cogs.value(ctx, period)
        yield Span(
            period,
            target_balance - lease_rou_assets.value(ctx, period.start),
            split_daily,
        )


lease_rou_assets = point.accumulate(
    *hist_balance_sheet.lease_rou_assets[0],
    lease_rou_assets_changes,
    label="Operating lease right-of-use assets",
)


total_ppe_cost = point.sum(
    [
        land,
        buildings,
        machinery_equipment,
        construction_in_progress,
        lease_rou_assets,
    ],
    label="Total Property, Plant and Equipment, at Cost",
)


@span.extend(balance_changes(hist_balance_sheet.accumulated_depreciation))
def accumulated_depreciation_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, ppe.depreciation.value(ctx, period), split_daily)


accumulated_depreciation = point.accumulate(
    *hist_balance_sheet.accumulated_depreciation[0],
    accumulated_depreciation_changes,
    label="Less - accumulated depreciation",
)


net_ppe = point.sub(
    total_ppe_cost,
    accumulated_depreciation,
    label="Net property, plant and equipment",
)


goodwill = flat_point(hist_balance_sheet.goodwill, "Goodwill")
trademarks = flat_point(hist_balance_sheet.trademarks, "Trademarks")


@span.extend(balance_changes(hist_balance_sheet.investments))
def investments_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        purchases = cash_flow.trading_security_purchases.value(
            ctx, period
        ) + cash_flow.afs_security_purchases.value(ctx, period)
        sales = cash_flow.trading_security_sales.value(
            ctx, period
        ) + cash_flow.afs_security_sales_maturities.value(ctx, period)
        amortization = cash_flow.sec_premium_amortization.value(ctx, period)
        yield Span(period, -purchases - sales - amortization, split_daily)


investments = point.accumulate(
    *hist_balance_sheet.investments[0],
    investments_changes,
    label="Investments",
)


@span.extend(balance_changes(hist_balance_sheet.prepaid_and_other_assets))
def prepaid_and_other_assets_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = prepaid_and_other_assets.value(
            ctx, prior_yr_period.end
        ) / income.total_revenue.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.total_revenue.value(ctx, period)
        yield Span(
            period,
            target_balance - prepaid_and_other_assets.value(ctx, period.start),
            split_daily,
        )


prepaid_and_other_assets = point.accumulate(
    *hist_balance_sheet.prepaid_and_other_assets[0],
    prepaid_and_other_assets_changes,
    label="Prepaid expenses and other assets",
)


@span.extend(balance_changes(hist_balance_sheet.deferred_income_taxes_noncurrent))
def deferred_income_taxes_noncurrent_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = deferred_income_taxes_noncurrent.value(
            ctx, prior_yr_period.end
        ) / income.income_tax_provision.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.income_tax_provision.value(ctx, period)
        yield Span(
            period,
            target_balance - deferred_income_taxes_noncurrent.value(ctx, period.start),
            split_daily,
        )


deferred_income_taxes_noncurrent = point.accumulate(
    *hist_balance_sheet.deferred_income_taxes_noncurrent[0],
    deferred_income_taxes_noncurrent_changes,
    label="Deferred income taxes - Noncurrent",
)


total_deferred_income_tax_assets = point.sum(
    [deferred_income_taxes_current, deferred_income_taxes_noncurrent],
    label="Total deferred income tax assets",
)


total_other_assets = point.sum(
    [
        goodwill,
        trademarks,
        investments,
        prepaid_and_other_assets,
        deferred_income_taxes_noncurrent,
    ],
    label="Total Other Assets",
)


total_assets = point.sum(
    [total_current_assets, net_ppe, total_other_assets],
    label="Total assets",
)


assets_stmt = Group(
    [
        Total(
            total_assets,
            [
                Total(
                    total_current_assets,
                    [
                        cash,
                        restricted_cash,
                        current_investments,
                        ar_trade_net,
                        other_receivables,
                        finished_goods_wip,
                        raw_materials_supplies,
                        prepaid_expenses,
                    ],
                ),
                Total(
                    net_ppe,
                    [
                        Total(
                            total_ppe_cost,
                            [
                                land,
                                buildings,
                                machinery_equipment,
                                construction_in_progress,
                                lease_rou_assets,
                            ],
                        ),
                        accumulated_depreciation,
                    ],
                ),
                Total(
                    total_other_assets,
                    [
                        goodwill,
                        trademarks,
                        investments,
                        prepaid_and_other_assets,
                        deferred_income_taxes_noncurrent,
                    ],
                ),
            ],
        )
    ],
)
