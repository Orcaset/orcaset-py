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
from . import dividends
from . import income
from .data import BalanceSheet

hist_balance_sheet = BalanceSheet()
c_qtr_offset = relativedelta(months=3)


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


common_stock = flat_point(
    hist_balance_sheet.common_stock,
    "Common stock, $0.694 par value",
)

class_b_common_stock = flat_point(
    hist_balance_sheet.class_b_common_stock,
    "Class B common stock, $0.694 par value",
)


@span.extend(balance_changes(hist_balance_sheet.capital_in_excess_of_par))
def capital_in_excess_of_par_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, cash_flow.share_repurchases.value(ctx, period), split_daily)


capital_in_excess_of_par = point.accumulate(
    *hist_balance_sheet.capital_in_excess_of_par[0],
    capital_in_excess_of_par_changes,
    label="Capital in excess of par value",
)


@span.extend(balance_changes(hist_balance_sheet.retained_earnings))
def retained_earnings_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(
            period,
            income.earnings_to_stockholders.value(ctx, period)
            - dividends.dividends_declared.value(ctx, period),
            split_daily,
        )


retained_earnings = point.accumulate(
    *hist_balance_sheet.retained_earnings[0],
    retained_earnings_changes,
    label="Retained earnings",
)


aoci_loss = flat_point(
    hist_balance_sheet.aoci_loss,
    "Accumulated Other Comprehensive Loss",
)

treasury_stock = flat_point(
    hist_balance_sheet.treasury_stock,
    "Treasury Stock (at Cost)",
)

shareholders_equity = point.sum(
    [
        common_stock,
        class_b_common_stock,
        capital_in_excess_of_par,
        retained_earnings,
        aoci_loss,
        treasury_stock,
    ],
    label="Total Tootsie Roll Industries, Inc. shareholders' equity",
)


@span.extend(balance_changes(hist_balance_sheet.noncontrolling_interests))
def noncontrolling_interests_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, income.nci_net_income.value(ctx, period), split_daily)


noncontrolling_interests = point.accumulate(
    *hist_balance_sheet.noncontrolling_interests[0],
    noncontrolling_interests_changes,
    label="Noncontrolling interests",
)

total_equity = point.sum(
    [shareholders_equity, noncontrolling_interests],
    label="Total equity",
)


equity_stmt = Group(
    [
        Total(
            total_equity,
            [
                Total(
                    shareholders_equity,
                    [
                        common_stock,
                        class_b_common_stock,
                        capital_in_excess_of_par,
                        retained_earnings,
                        aoci_loss,
                        treasury_stock,
                    ],
                ),
                noncontrolling_interests,
            ],
        )
    ],
)
