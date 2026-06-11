from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from itertools import takewhile
from math import ceil

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    KeyedSpanSeries,
    Period,
    Span,
    SpanSeriesDef,
    no_split,
    span,
    split_daily,
    sum_spans,
)

from .assumptions import get_assumptions
from .data import BalanceSheet, CashFlow, PointData, SpanData

hist_balance_sheet = BalanceSheet()
hist_cash_flow = CashFlow()

c_qtr_offset = relativedelta(months=3, day=31)
projection_start = hist_balance_sheet.buildings[-1][0]


def recent_qtr_avg(values: SpanData, qtrs: int, label: str) -> float:
    recent = [value for _, value in values[-qtrs:] if value is not None]
    if len(recent) != qtrs:
        raise ValueError(f"Expected {qtrs} quarters of historical {label}")
    return sum(recent) / qtrs


def latest_balance(values: PointData, label: str) -> float:
    value = values[-1][1]
    if value is None:
        raise ValueError(f"Missing latest {label} balance")
    return value


def balance_growth(values: PointData, label: str) -> float:
    first, last = values[0][1], values[-1][1]
    if first is None or last is None:
        raise ValueError(f"Missing {label} balances")
    return last - first


# ----- Capital expenditures -----
# Projected as the average of the last two historical years (eight quarters).

hist_capex = span.from_list(hist_cash_flow.capex, agg=sum_spans(0.0), split=no_split)
avg_qtr_capex = recent_qtr_avg(hist_cash_flow.capex, 8, "capital expenditures")


@span.extend(hist_capex, label="Capital expenditures")
def capex(_: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, c_qtr_offset):
        yield Span(period, Formula.pure(avg_qtr_capex), split_daily)


# Split between buildings and machinery by each class's share of gross balance
# growth over the historical window, unless overridden by assumption. Capex is
# negative in the cash flow data, so class capex is flipped to positive additions.
buildings_gross_growth = balance_growth(hist_balance_sheet.buildings, "buildings")
machinery_gross_growth = balance_growth(
    hist_balance_sheet.machinery_equipment, "machinery and equipment"
)

default_building_capex_share = buildings_gross_growth / (
    buildings_gross_growth + machinery_gross_growth
)


def building_capex_share(ctx: Context) -> float:
    override = get_assumptions(ctx).ppe.building_capex_share
    return override if override is not None else default_building_capex_share


def class_capex(share: Callable[[Context], float], label: str) -> SpanSeriesDef:
    @span.define(agg=sum_spans(0.0), label=label)
    def class_capex_spans(ctx: Context) -> Iterable[Span]:
        class_share = share(ctx)
        for period, _ in hist_cash_flow.capex:
            yield Span(period, capex.value(ctx, period) * -class_share, no_split)
        for period in Period.seq(hist_cash_flow.capex[-1][0].end, c_qtr_offset):
            yield Span(period, capex.value(ctx, period) * -class_share, split_daily)

    return class_capex_spans


building_capex = class_capex(building_capex_share, "Building capital expenditures")
machinery_capex = class_capex(
    lambda ctx: 1.0 - building_capex_share(ctx), "Machinery capital expenditures"
)


# ----- Depreciation of existing PPE -----
# TR does not disclose the class split of accumulated depreciation or a runoff
# schedule, so the existing pool is run off as a single cohort: the net
# depreciable base depreciates at the trailing-year reported run-rate until
# exhausted, keeping projected depreciation continuous with historicals.

existing_net_ppe = (
    latest_balance(hist_balance_sheet.buildings, "buildings")
    + latest_balance(hist_balance_sheet.machinery_equipment, "machinery and equipment")
    - latest_balance(hist_balance_sheet.accumulated_depreciation, "accumulated depreciation")
)
existing_qtr_depreciation = recent_qtr_avg(hist_cash_flow.depreciation, 4, "depreciation")


@span.define(agg=sum_spans(0.0), label="Existing PPE depreciation")
def existing_depreciation(_: Context) -> Iterable[Span]:
    remaining = existing_net_ppe
    for period in Period.seq(projection_start, c_qtr_offset):
        amount = min(existing_qtr_depreciation, remaining)
        remaining -= amount
        yield Span(period, Formula.pure(amount), split_daily)


# ----- Depreciation of new capex -----
# Each projected quarter of class capex becomes a cohort depreciating
# straight-line over the class useful life, starting the following quarter.


def capex_cohort_keys(period: Period) -> Iterable[Period]:
    yield from takewhile(lambda p: p.start < period.end, Period.seq(projection_start, c_qtr_offset))


def capex_depreciation_cohorts(
    class_capex_series: SpanSeriesDef, useful_life_years: Callable[[Context], float], label: str
) -> KeyedSpanSeries[Period]:
    def cohort_series(cohort: Period) -> SpanSeriesDef:
        @span.define(agg=sum_spans(0.0), label=f"{label} ({cohort} capex)")
        def depreciation_cohort(ctx: Context) -> Iterable[Span]:
            life_qtrs = ceil(useful_life_years(ctx) * 4)
            quarterly: Formula[float | None] = class_capex_series.value(ctx, cohort).map(
                lambda value: None if value is None else value / life_qtrs
            )
            for period in Period.seq(
                cohort.end, c_qtr_offset, cohort.end + (c_qtr_offset * life_qtrs)
            ):
                yield Span(period, quarterly, split_daily)

        return depreciation_cohort

    return span.keyed(keys=capex_cohort_keys, series=cohort_series, label=f"{label} cohorts")


def cohort_total(cohorts: KeyedSpanSeries[Period], label: str) -> SpanSeriesDef:
    @span.define(agg=sum_spans(0.0), label=label)
    def total_depreciation(ctx: Context) -> Iterable[Span]:
        for period in Period.seq(projection_start, c_qtr_offset):
            cohort_values = [series.value(ctx, period) for _, series in cohorts.items(ctx, period)]
            total: Formula[float | None] = Formula.sequence(cohort_values).map(
                lambda values: float(sum(value or 0.0 for value in values))
            )
            yield Span(period, total, no_split)

    return total_depreciation


building_depreciation_cohorts = capex_depreciation_cohorts(
    building_capex,
    lambda ctx: get_assumptions(ctx).ppe.buildings_useful_life_years,
    "Building depr",
)
machinery_depreciation_cohorts = capex_depreciation_cohorts(
    machinery_capex,
    lambda ctx: get_assumptions(ctx).ppe.machinery_useful_life_years,
    "Machinery depr",
)

building_depreciation = cohort_total(building_depreciation_cohorts, "Building depr")
machinery_depreciation = cohort_total(machinery_depreciation_cohorts, "Machinery depr")


# ----- Total depreciation -----

hist_depreciation = span.from_list(hist_cash_flow.depreciation, agg=sum_spans(0.0), split=no_split)
projected_depreciation = span.sum(
    [existing_depreciation, building_depreciation, machinery_depreciation],
    agg=sum_spans(0.0),
    label="Projected depreciation",
)
depreciation = hist_depreciation.then(projected_depreciation, label="Depreciation")
