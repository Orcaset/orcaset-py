from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from itertools import takewhile
from math import ceil

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

from .assumptions import Assumptions
from .data import BalanceSheet, CashFlow
from .income import total_revenue

hist_balance_sheet = BalanceSheet()
hist_cash_flow = CashFlow()

c_qtr_offset = relativedelta(months=3, day=31)
yr_lookback = relativedelta(years=-1)
projection_start = hist_balance_sheet.buildings[-1][0]


hist_capex = span.from_list(hist_cash_flow.capex, agg=sum_spans(0.0), split=no_split)


@span.extend(hist_capex, label="Capital expenditures")
def capex(ctx: Context, start: date) -> Iterable[Span]:
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


latest_buildings = hist_balance_sheet.buildings[-1][1] or 0.0
latest_machinery = hist_balance_sheet.machinery_equipment[-1][1] or 0.0
latest_accumulated_depreciation = hist_balance_sheet.accumulated_depreciation[-1][1] or 0.0
gross_depreciable_ppe = latest_buildings + latest_machinery

building_capex_share = (
    Assumptions.PPE.building_capex_share
    if Assumptions.PPE.building_capex_share is not None
    else latest_buildings / gross_depreciable_ppe
    if gross_depreciable_ppe
    else 0.0
)
machinery_capex_share = 1.0 - building_capex_share

building_depreciation_weight = (
    latest_buildings / Assumptions.PPE.buildings_useful_life_years
    if Assumptions.PPE.buildings_useful_life_years
    else 0.0
)
machinery_depreciation_weight = (
    latest_machinery / Assumptions.PPE.machinery_useful_life_years
    if Assumptions.PPE.machinery_useful_life_years
    else 0.0
)
depreciation_weight_total = building_depreciation_weight + machinery_depreciation_weight
building_accumulated_depreciation = (
    latest_accumulated_depreciation * building_depreciation_weight / depreciation_weight_total
    if depreciation_weight_total
    else 0.0
)
machinery_accumulated_depreciation = (
    latest_accumulated_depreciation * machinery_depreciation_weight / depreciation_weight_total
    if depreciation_weight_total
    else 0.0
)
existing_buildings_net = max(0.0, latest_buildings - building_accumulated_depreciation)
existing_machinery_net = max(0.0, latest_machinery - machinery_accumulated_depreciation)


building_capex = capex.scale(-building_capex_share, label="Building capital expenditures")
machinery_capex = capex.scale(-machinery_capex_share, label="Machinery capital expenditures")

type DepreciationCohortKey = tuple[str, str | Period]


def building_depreciation_cohort_series(key: DepreciationCohortKey) -> SpanSeriesDef:
    kind, cohort = key

    @span.define(agg=sum_spans(0.0), label=f"Building depreciation - {kind} {cohort}")
    def depreciation_cohort(ctx: Context) -> Iterable[Span]:
        if kind == "existing":
            depreciation_base: Formula[float | None] = Formula.pure(existing_buildings_net)
            life_qtrs = ceil(Assumptions.PPE.buildings_remaining_life_years * 4)
            first_period_start = projection_start
        else:
            assert isinstance(cohort, Period)
            depreciation_base = building_capex.value(ctx, cohort)
            life_qtrs = ceil(Assumptions.PPE.buildings_useful_life_years * 4)
            first_period_start = cohort.end

        quarterly_depreciation: Formula[float | None] = (
            depreciation_base.map(lambda value: None if value is None else value / life_qtrs)
            if life_qtrs
            else Formula.pure(0.0)
        )
        for period in Period.seq(
            first_period_start,
            c_qtr_offset,
            first_period_start + (c_qtr_offset * life_qtrs),
        ):
            yield Span(period, quarterly_depreciation, split_daily)

    return depreciation_cohort


def machinery_depreciation_cohort_series(key: DepreciationCohortKey) -> SpanSeriesDef:
    kind, cohort = key

    @span.define(agg=sum_spans(0.0), label=f"Machinery depreciation - {kind} {cohort}")
    def depreciation_cohort(ctx: Context) -> Iterable[Span]:
        if kind == "existing":
            depreciation_base: Formula[float | None] = Formula.pure(existing_machinery_net)
            life_qtrs = ceil(Assumptions.PPE.machinery_remaining_life_years * 4)
            first_period_start = projection_start
        else:
            assert isinstance(cohort, Period)
            depreciation_base = machinery_capex.value(ctx, cohort)
            life_qtrs = ceil(Assumptions.PPE.machinery_useful_life_years * 4)
            first_period_start = cohort.end

        quarterly_depreciation: Formula[float | None] = (
            depreciation_base.map(lambda value: None if value is None else value / life_qtrs)
            if life_qtrs
            else Formula.pure(0.0)
        )
        for period in Period.seq(
            first_period_start,
            c_qtr_offset,
            first_period_start + (c_qtr_offset * life_qtrs),
        ):
            yield Span(period, quarterly_depreciation, split_daily)

    return depreciation_cohort


def depreciation_cohort_keys(period: Period) -> Iterable[DepreciationCohortKey]:
    yield ("existing", "existing")
    for cohort in takewhile(
        lambda p: p.start < period.end, Period.seq(projection_start, c_qtr_offset)
    ):
        yield ("capex", cohort)


building_depreciation_cohorts = span.keyed(
    keys=depreciation_cohort_keys,
    series=building_depreciation_cohort_series,
    label="Building depreciation cohorts",
)

machinery_depreciation_cohorts = span.keyed(
    keys=depreciation_cohort_keys,
    series=machinery_depreciation_cohort_series,
    label="Machinery depreciation cohorts",
)


@span.define(agg=sum_spans(0.0), label="Building depreciation")
def building_depreciation(ctx: Context) -> Iterable[Span]:
    for period in Period.seq(projection_start, c_qtr_offset):
        cohorts = building_depreciation_cohorts.items(ctx, period)
        cohort_values = [cohort.value(ctx, period) for _, cohort in cohorts]
        total: Formula[float | None] = Formula.sequence(cohort_values).map(
            lambda values: float(sum(value or 0.0 for value in values))
        )
        yield Span(period, total, no_split)


@span.define(agg=sum_spans(0.0), label="Machinery depreciation")
def machinery_depreciation(ctx: Context) -> Iterable[Span]:
    for period in Period.seq(projection_start, c_qtr_offset):
        cohorts = machinery_depreciation_cohorts.items(ctx, period)
        cohort_values = [cohort.value(ctx, period) for _, cohort in cohorts]
        total: Formula[float | None] = Formula.sequence(cohort_values).map(
            lambda values: float(sum(value or 0.0 for value in values))
        )
        yield Span(period, total, no_split)


hist_depreciation = span.from_list(hist_cash_flow.depreciation, agg=sum_spans(0.0), split=no_split)
projected_depreciation = span.sum(
    [building_depreciation, machinery_depreciation],
    agg=sum_spans(0.0),
    label="Projected depreciation",
)
depreciation = hist_depreciation.then(projected_depreciation, label="Depreciation")
