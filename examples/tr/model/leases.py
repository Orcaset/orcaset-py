from collections.abc import Iterable
from datetime import date
from itertools import pairwise
from math import ceil

from dateutil.relativedelta import relativedelta

from orcaset import Context, Formula, Period, Span, no_split, point, span, split_daily, sum_spans

from .assumptions import Assumptions
from .data import BalanceSheet

hist_balance_sheet = BalanceSheet()

c_qtr_offset = relativedelta(months=3)


def _balance_changes(values: list[tuple[date, float | None]]):
    changes = [
        (
            Period(prev[0], curr[0]),
            curr[1] - prev[1] if curr[1] is not None and prev[1] is not None else None,
        )
        for prev, curr in pairwise(values)
    ]
    return span.from_list(changes, agg=sum_spans(0.0), split=no_split)


def _latest_average_decrease(values: list[tuple[date, float | None]], count: int = 4) -> float:
    changes = [
        prev[1] - curr[1]
        for prev, curr in pairwise(values)
        if curr[1] is not None and prev[1] is not None and curr[1] < prev[1]
    ]
    latest_changes = changes[-count:]
    return sum(latest_changes) / len(latest_changes) if latest_changes else 0.0


lease_liability_data = [
    (
        current[0],
        (current[1] or 0.0) + (noncurrent[1] or 0.0)
        if current[1] is not None or noncurrent[1] is not None
        else None,
    )
    for current, noncurrent in zip(
        hist_balance_sheet.lease_liabilities,
        hist_balance_sheet.lease_liabilities_noncurrent,
        strict=True,
    )
]

latest_date = hist_balance_sheet.lease_rou_assets[-1][0]
latest_rou_asset = hist_balance_sheet.lease_rou_assets[-1][1] or 0.0
historical_rou_runoff = _latest_average_decrease(hist_balance_sheet.lease_rou_assets)

lease_runoff_qtrs = (
    ceil(Assumptions.Leases.remaining_life_years * 4)
    if Assumptions.Leases.remaining_life_years is not None
    else ceil(latest_rou_asset / historical_rou_runoff)
    if historical_rou_runoff
    else 0
)
quarterly_lease_runoff = latest_rou_asset / lease_runoff_qtrs if lease_runoff_qtrs else 0.0
current_liability_amount = quarterly_lease_runoff * Assumptions.Leases.current_liability_quarters


@span.extend(
    _balance_changes(hist_balance_sheet.lease_rou_assets), label="Operating lease ROU changes"
)
def lease_rou_asset_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_balance = lease_rou_asset.value(ctx, period.start)
        yield Span(
            period,
            prior_balance.map(
                lambda value: None if value is None else -min(value, quarterly_lease_runoff)
            ),
            split_daily,
        )


lease_rou_asset = point.accumulate(
    *hist_balance_sheet.lease_rou_assets[0],
    lease_rou_asset_changes,
    label="Operating lease right-of-use assets",
)


@span.extend(_balance_changes(lease_liability_data), label="Operating lease liability changes")
def total_lease_liability_changes(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        prior_balance = total_lease_liability.value(ctx, period.start)
        yield Span(
            period,
            prior_balance.map(
                lambda value: None if value is None else -min(value, quarterly_lease_runoff)
            ),
            split_daily,
        )


total_lease_liability = point.accumulate(
    *lease_liability_data[0],
    total_lease_liability_changes,
    label="Total operating lease liabilities",
)

current_lease_liabilities_by_date = dict(hist_balance_sheet.lease_liabilities)
noncurrent_lease_liabilities_by_date = dict(hist_balance_sheet.lease_liabilities_noncurrent)


@point.define(label="Current - Operating lease liabilities")
def current_lease_liability(ctx: Context, dt: date) -> Formula[float | None]:
    if dt <= latest_date:
        return Formula.pure(current_lease_liabilities_by_date.get(dt))

    return total_lease_liability.value(ctx, dt).map(
        lambda value: None if value is None else min(value, current_liability_amount)
    )


@point.define(label="Noncurrent - Operating lease liabilities")
def noncurrent_lease_liability(ctx: Context, dt: date) -> Formula[float | None]:
    if dt <= latest_date:
        return Formula.pure(noncurrent_lease_liabilities_by_date.get(dt))

    return total_lease_liability.value(ctx, dt) - current_lease_liability.value(ctx, dt)
