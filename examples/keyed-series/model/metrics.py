"""Customer count projections by size group for each scenario."""

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

from .assumptions import SCENARIOS, customer_growth
from .data import group_keys, hist_metrics, hist_start

qtr_offset = relativedelta(months=3, day=31)
qtr_lookback = relativedelta(months=-3, day=31)


def _customers_series(scenario: str, group: str) -> SpanSeriesDef:
    growth = customer_growth[scenario][group]

    @span.extend(hist_metrics["customers"][group], label=f"Customers | {group}")
    def projected(ctx: Context, start: date) -> Iterable[Span]:
        for period in Period.seq(start, qtr_offset):
            prior = projected.value(ctx, period.from_start(qtr_lookback))
            # Annual YoY growth assumption compounded quarterly.
            qtr_factor = growth.value(ctx, period).map(
                lambda g: None if g is None else (1.0 + g / 100.0) ** 0.25
            )
            yield Span(period, prior * qtr_factor, split_daily)

    return projected


customers: dict[str, dict[str, SpanSeriesDef]] = {
    scenario: {group: _customers_series(scenario, group) for group in group_keys}
    for scenario in SCENARIOS
}


def _total_customers_series(scenario: str) -> SpanSeriesDef:
    @span.define(agg=sum_spans(0.0), label="Total Customers")
    def total_customers(ctx: Context) -> Iterable[Span]:
        for period in Period.seq(hist_start, qtr_offset):
            values = [customers[scenario][group].value(ctx, period) for group in group_keys]
            total: Formula[float | None] = Formula.sequence(values).map(
                lambda vals: sum(v or 0.0 for v in vals)
            )
            yield Span(period, total, split_daily)

    return total_customers


total_customers: dict[str, SpanSeriesDef] = {
    scenario: _total_customers_series(scenario) for scenario in SCENARIOS
}

customer_groups: dict[str, KeyedSpanSeries[str]] = {
    scenario: span.keyed(
        keys=lambda _: group_keys,
        series=lambda group, scenario=scenario: customers[scenario][group],
        label="Customers by group",
    )
    for scenario in SCENARIOS
}
