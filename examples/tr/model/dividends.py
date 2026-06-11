from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Period,
    Span,
    SpanSeriesDef,
    no_split,
    span,
    split_daily,
    sum_spans,
)

from .data import BalanceSheet, CashFlow
from .income import earnings_to_stockholders

hist_balance_sheet = BalanceSheet()
hist_cash_flow = CashFlow()

c_qtr_offset = relativedelta(months=3, day=31)
yr_lookback = relativedelta(years=-1)


def _project_from_prior_year_earnings(
    ctx: Context,
    period: Period,
    series: SpanSeriesDef,
) -> Formula[float | None]:
    prior_period = period.shift(yr_lookback)

    def project(values: tuple[float | None, ...]) -> float | None:
        prior_value, prior_earnings, current_earnings = values
        if (
            prior_value is None
            or prior_earnings is None
            or prior_earnings == 0.0
            or current_earnings is None
        ):
            return 0.0
        return current_earnings * (prior_value / prior_earnings)

    return Formula.sequence(
        [
            series.value(ctx, prior_period),
            earnings_to_stockholders.value(ctx, prior_period),
            earnings_to_stockholders.value(ctx, period),
        ]
    ).map(project)


hist_dividends_paid = span.from_list(
    hist_cash_flow.dividends_paid,
    agg=sum_spans(0.0),
    split=no_split,
)


@span.extend(hist_dividends_paid, label="Dividends paid in cash")
def dividends_paid(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period, _project_from_prior_year_earnings(ctx, period, dividends_paid), split_daily
        )


dividends_payable_by_date = dict(hist_balance_sheet.dividends_payable)
dividends_declared_data: list[tuple[Period, float | None]] = []
for period, dividends_paid_value in hist_cash_flow.dividends_paid:
    beginning_payable = dividends_payable_by_date.get(period.start)
    ending_payable = dividends_payable_by_date.get(period.end)
    if beginning_payable is None or ending_payable is None or dividends_paid_value is None:
        dividends_declared_data.append((period, None))
    else:
        dividends_declared_data.append(
            (period, ending_payable - beginning_payable - dividends_paid_value)
        )

hist_dividends_declared = span.from_list(
    dividends_declared_data,
    agg=sum_spans(0.0),
    split=no_split,
)


@span.extend(hist_dividends_declared, label="Dividends declared")
def dividends_declared(ctx: Context, start: date) -> Iterable[Span]:
    from .liabilities import dividends_payable

    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            dividends_payable.value(ctx, period.end)
            - dividends_payable.value(ctx, period.start)
            - dividends_paid.value(ctx, period),
            split_daily,
        )
