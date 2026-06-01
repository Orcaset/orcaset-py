from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Period,
    Span,
    SpanSeriesDef,
    Stmt,
    Total,
    fixed_width_table,
    span,
    split_daily,
    sum_spans,
)


# --------------- ASSUMPTIONS ---------------
quarter = relativedelta(months=3, day=31)
model_start = date(2025, 12, 31)
model_end = date(2027, 12, 31)
useful_life_qtrs = 4


# ------------------ CAPEX ------------------
CapEx = span.periodic(
    model_start,
    quarter,
    100.0,
    agg=sum_spans(0.0),
    split=split_daily,
    end=model_end,
    label="Capital Expenditures",
)


def quarter_label(cohort: Period) -> str:
    return f"{cohort.end:%Y} Q{((cohort.end.month - 1) // 3) + 1}"


def depreciation_cohort(cohort: Period) -> SpanSeriesDef:
    """Create one depreciation schedule line for a capex cohort."""

    @span.define(agg=sum_spans(0.0), label=f"Depreciation {quarter_label(cohort)}")
    def DepreciationCohort(ctx: Context) -> Iterable[Span]:
        capex = CapEx.value(ctx, cohort)
        depreciation = capex / useful_life_qtrs

        for index in range(useful_life_qtrs):
            yield Span(cohort.shift(quarter * index), depreciation, split_daily)

    return DepreciationCohort


cohorts = Period.list(model_start, quarter, model_end)
DepreciationCohorts = [depreciation_cohort(cohort) for cohort in cohorts]


@span.define(agg=sum_spans(0.0), label="Total Depreciation")
def TotalDepreciation(ctx: Context) -> Iterable[Span]:
    for period in Period.seq(model_start, quarter):
        cohort_values = [cohort.value(ctx, period) for cohort in DepreciationCohorts]
        total: Formula[float | None] = Formula.pure(0.0)
        for value in cohort_values:
            total = total.map2(value, lambda left, right: (left or 0.0) + (right or 0.0))
        yield Span(period, total, split_daily)


# ------------- STRUCTURED OUTPUT -------------
ctx = Context()
stmt = Stmt(
    CapEx,
    Total(TotalDepreciation, DepreciationCohorts),
)

periods = Period.list(model_start, quarter, model_end)
results = stmt.values(ctx, periods)
print(fixed_width_table(results, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))
