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
from .data import BalanceSheet

hist_balance_sheet = BalanceSheet()
c_qtr_offset = relativedelta(months=3)
yr_lookback = relativedelta(years=-1)


def fill_blanks(values: list[tuple[date, float | None]]) -> list[tuple[date, float | None]]:
    return [(dt, 0.0 if value is None else value) for dt, value in values]


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


def zero_point(values: list[tuple[date, float | None]], label: str) -> PointSeriesDef:
    start = values[0][0]

    @point.define(label=label)
    def series(_: Context, dt: date) -> Formula[float | None]:
        return Formula.pure(0.0 if dt >= start else None)

    return series


def flat_point(values: list[tuple[date, float | None]], label: str) -> PointSeriesDef:
    @span.extend(balance_changes(fill_blanks(values)), label=f"{label} changes")
    def changes(_: Context, start: date) -> Iterable[Span]:
        for period in Period.seq(start, c_qtr_offset):
            yield Span(period, Formula.pure(0.0), split_daily)

    return point.accumulate(*fill_blanks(values)[0], changes, label=label)


@span.extend(balance_changes(hist_balance_sheet.accounts_payable))
def accounts_payable_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = accounts_payable.value(ctx, prior_yr_period.end) / income.total_cogs.value(
            ctx, prior_yr_period
        )
        target_balance = prior_yr_ratio * income.total_cogs.value(ctx, period)
        yield Span(period, target_balance - accounts_payable.value(ctx, period.start), split_daily)


accounts_payable = point.accumulate(
    *hist_balance_sheet.accounts_payable[0],
    accounts_payable_changes,
    label="Accounts Payable",
)


@span.extend(balance_changes(hist_balance_sheet.bank_loans))
def bank_loans_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            cash_flow.bank_loan_proceeds.value(ctx, period)
            + cash_flow.bank_loan_repayments.value(ctx, period),
            split_daily,
        )


bank_loans = point.accumulate(
    *hist_balance_sheet.bank_loans[0],
    bank_loans_changes,
    label="Bank Loans - Current",
)


@span.extend(balance_changes(hist_balance_sheet.dividends_payable))
def dividends_payable_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = dividends_payable.value(
            ctx, prior_yr_period.end
        ) / income.earnings_to_stockholders.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.earnings_to_stockholders.value(ctx, period)
        yield Span(
            period,
            target_balance - dividends_payable.value(ctx, period.start),
            split_daily,
        )


dividends_payable = point.accumulate(
    *hist_balance_sheet.dividends_payable[0],
    dividends_payable_changes,
    label="Dividends payable",
)


@span.extend(balance_changes(hist_balance_sheet.accrued_liabilities))
def accrued_liabilities_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = accrued_liabilities.value(
            ctx, prior_yr_period.end
        ) / income.total_revenue.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.total_revenue.value(ctx, period)
        yield Span(
            period, target_balance - accrued_liabilities.value(ctx, period.start), split_daily
        )


accrued_liabilities = point.accumulate(
    *hist_balance_sheet.accrued_liabilities[0],
    accrued_liabilities_changes,
    label="Accrued Liabilities",
)


postretirement_benefits = flat_point(
    hist_balance_sheet.postretirement_benefits,
    "Postretirement health care benefits - Current",
)

deferred_income_taxes_current_liab = zero_point(
    hist_balance_sheet.deferred_income_taxes_current_liab,
    "Deferred Income Taxes (liability) - Current",
)


@span.extend(balance_changes(hist_balance_sheet.lease_liabilities))
def lease_liabilities_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = lease_liabilities.value(
            ctx, prior_yr_period.end
        ) / income.total_cogs.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.total_cogs.value(ctx, period)
        yield Span(
            period,
            target_balance - lease_liabilities.value(ctx, period.start),
            split_daily,
        )


lease_liabilities = point.accumulate(
    *hist_balance_sheet.lease_liabilities[0],
    lease_liabilities_changes,
    label="Operating lease liabilities - Current",
)


income_taxes_payable_data = fill_blanks(hist_balance_sheet.income_taxes_payable)


@span.extend(balance_changes(income_taxes_payable_data))
def income_taxes_payable_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = income_taxes_payable.value(
            ctx, prior_yr_period.end
        ) / income.income_tax_provision.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.income_tax_provision.value(ctx, period)
        yield Span(
            period,
            target_balance - income_taxes_payable.value(ctx, period.start),
            split_daily,
        )


income_taxes_payable = point.accumulate(
    *income_taxes_payable_data[0],
    income_taxes_payable_changes,
    label="Income taxes payable",
)


uncertain_tax_positions_current = zero_point(
    hist_balance_sheet.uncertain_tax_positions_current,
    "Liability for Uncertain Tax Positions - Current",
)


deferred_compensation_data = fill_blanks(hist_balance_sheet.deferred_compensation)


@span.extend(balance_changes(deferred_compensation_data))
def deferred_compensation_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = deferred_compensation.value(
            ctx, prior_yr_period.end
        ) / income.total_revenue.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.total_revenue.value(ctx, period)
        yield Span(
            period,
            target_balance - deferred_compensation.value(ctx, period.start),
            split_daily,
        )


deferred_compensation = point.accumulate(
    *deferred_compensation_data[0],
    deferred_compensation_changes,
    label="Deferred compensation",
)


total_current_liabilities = point.sum(
    [
        accounts_payable,
        bank_loans,
        dividends_payable,
        accrued_liabilities,
        postretirement_benefits,
        deferred_income_taxes_current_liab,
        lease_liabilities,
        income_taxes_payable,
        uncertain_tax_positions_current,
        deferred_compensation,
    ],
    label="Total current liabilities",
)


@span.extend(balance_changes(hist_balance_sheet.deferred_income_taxes_noncurrent_liab))
def deferred_income_taxes_noncurrent_liab_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = deferred_income_taxes_noncurrent_liab.value(
            ctx, prior_yr_period.end
        ) / income.income_tax_provision.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.income_tax_provision.value(ctx, period)
        yield Span(
            period,
            target_balance - deferred_income_taxes_noncurrent_liab.value(ctx, period.start),
            split_daily,
        )


deferred_income_taxes_noncurrent_liab = point.accumulate(
    *hist_balance_sheet.deferred_income_taxes_noncurrent_liab[0],
    deferred_income_taxes_noncurrent_liab_changes,
    label="Deferred income taxes (liability) - Noncurrent",
)


total_deferred_income_tax_liabilities = point.sum(
    [deferred_income_taxes_current_liab, deferred_income_taxes_noncurrent_liab],
    label="Total deferred income tax liabilities",
)


bank_loans_noncurrent = zero_point(
    hist_balance_sheet.bank_loans_noncurrent,
    "Bank Loans - Noncurrent",
)

postretirement_benefits_noncurrent = flat_point(
    hist_balance_sheet.postretirement_benefits_noncurrent,
    "Postretirement health care benefits - Noncurrent",
)

industrial_development_bonds = flat_point(
    hist_balance_sheet.industrial_development_bonds,
    "Industrial development bonds",
)

uncertain_tax_positions_noncurrent = flat_point(
    hist_balance_sheet.uncertain_tax_positions_noncurrent,
    "Liability for uncertain tax positions - Noncurrent",
)


@span.extend(balance_changes(hist_balance_sheet.lease_liabilities_noncurrent))
def lease_liabilities_noncurrent_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = lease_liabilities_noncurrent.value(
            ctx, prior_yr_period.end
        ) / income.total_cogs.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.total_cogs.value(ctx, period)
        yield Span(
            period,
            target_balance - lease_liabilities_noncurrent.value(ctx, period.start),
            split_daily,
        )


lease_liabilities_noncurrent = point.accumulate(
    *hist_balance_sheet.lease_liabilities_noncurrent[0],
    lease_liabilities_noncurrent_changes,
    label="Operating lease liabilities - Noncurrent",
)


@span.extend(balance_changes(hist_balance_sheet.deferred_comp_and_other_liabilities))
def deferred_comp_and_other_liabilities_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_yr_period = period.shift(yr_lookback)
        prior_yr_ratio = deferred_comp_and_other_liabilities.value(
            ctx, prior_yr_period.end
        ) / income.total_revenue.value(ctx, prior_yr_period)
        target_balance = prior_yr_ratio * income.total_revenue.value(ctx, period)
        yield Span(
            period,
            target_balance - deferred_comp_and_other_liabilities.value(ctx, period.start),
            split_daily,
        )


deferred_comp_and_other_liabilities = point.accumulate(
    *hist_balance_sheet.deferred_comp_and_other_liabilities[0],
    deferred_comp_and_other_liabilities_changes,
    label="Deferred compensation and other liabilities",
)


total_noncurrent_liabilities = point.sum(
    [
        deferred_income_taxes_noncurrent_liab,
        bank_loans_noncurrent,
        postretirement_benefits_noncurrent,
        industrial_development_bonds,
        uncertain_tax_positions_noncurrent,
        lease_liabilities_noncurrent,
        deferred_comp_and_other_liabilities,
    ],
    label="Total noncurrent liabilities",
)


total_liabilities = point.sum(
    [total_current_liabilities, total_noncurrent_liabilities],
    label="Total Liabilities",
)


liabilities_stmt = Group(
    [
        Total(
            total_liabilities,
            [
                Total(
                    total_current_liabilities,
                    [
                        accounts_payable,
                        bank_loans,
                        dividends_payable,
                        accrued_liabilities,
                        postretirement_benefits,
                        deferred_income_taxes_current_liab,
                        lease_liabilities,
                        income_taxes_payable,
                        uncertain_tax_positions_current,
                        deferred_compensation,
                    ],
                ),
                Total(
                    total_noncurrent_liabilities,
                    [
                        deferred_income_taxes_noncurrent_liab,
                        bank_loans_noncurrent,
                        postretirement_benefits_noncurrent,
                        industrial_development_bonds,
                        uncertain_tax_positions_noncurrent,
                        lease_liabilities_noncurrent,
                        deferred_comp_and_other_liabilities,
                    ],
                ),
            ],
        )
    ],
)
