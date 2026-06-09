"""Revenue projections by size group for each scenario.

Per-group quarterly build:

    revenue[q] = revenue[q-1] * NDR^(1/4)              # existing base, net of expansion/churn
               + new_customers[q] * entry_arpc * 0.5   # new logos, half-quarter convention

`entry_arpc` is the group's average quarterly revenue per customer over the last
historical quarter, i.e. new customers are assumed to land at the segment average.
"""

from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    KeyedSpanSeries,
    Period,
    Span,
    SpanSeriesDef,
    span,
    split_daily,
    sum_spans,
)

from .assumptions import SCENARIOS, ndr
from .data import group_keys, hist_metrics, hist_revenue, hist_start, last_hist_period
from .metrics import customers

qtr_offset = relativedelta(months=3, day=31)
qtr_lookback = relativedelta(months=-3, day=31)


def _revenue_series(scenario: str, group: str) -> SpanSeriesDef:
    group_ndr = ndr[scenario][group]
    group_customers = customers[scenario][group]

    @span.extend(hist_revenue[group], label=f"Revenue | {group}")
    def projected(ctx: Context, start: date) -> Iterable[Span]:
        entry_arpc = hist_revenue[group].value(ctx, last_hist_period) / hist_metrics["customers"][
            group
        ].value(ctx, last_hist_period)

        for period in Period.seq(start, qtr_offset):
            prior_period = period.from_start(qtr_lookback)
            prior_revenue = projected.value(ctx, prior_period)
            # Annual NDR assumption applied quarterly.
            ndr_factor = group_ndr.value(ctx, period).map(
                lambda n: None if n is None else (n / 100.0) ** 0.25
            )
            new_customers = group_customers.value(ctx, period) - group_customers.value(
                ctx, prior_period
            )
            yield Span(
                period,
                prior_revenue * ndr_factor + new_customers * entry_arpc * 0.5,
                split_daily,
            )

    return projected


revenue: dict[str, dict[str, SpanSeriesDef]] = {
    scenario: {group: _revenue_series(scenario, group) for group in group_keys}
    for scenario in SCENARIOS
}


def _total_revenue_series(scenario: str) -> SpanSeriesDef:
    @span.define(agg=sum_spans(0.0), label="Total Revenue")
    def total_revenue(ctx: Context) -> Iterable[Span]:
        for period in Period.seq(hist_start, qtr_offset):
            values = [revenue[scenario][group].value(ctx, period) for group in group_keys]
            total: Formula[float | None] = Formula.sequence(values).map(
                lambda vals: sum(v or 0.0 for v in vals)
            )
            yield Span(period, total, split_daily)

    return total_revenue


total_revenue: dict[str, SpanSeriesDef] = {
    scenario: _total_revenue_series(scenario) for scenario in SCENARIOS
}

revenue_groups: dict[str, KeyedSpanSeries[str]] = {
    scenario: span.keyed(
        keys=lambda _: group_keys,
        series=lambda group, scenario=scenario: revenue[scenario][group],
        label="Revenue by group",
    )
    for scenario in SCENARIOS
}
