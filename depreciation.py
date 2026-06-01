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
    no_split,
    split_const,
    span,
    sum_spans,
)


quarter = relativedelta(months=3, day=31)
model_start = date(2025, 12, 31)
capex_cohort_end = date(2026, 6, 30)
useful_life_qtrs = 4


CapEx = span.from_list(
    [
        ((model_start, model_start + quarter), 200.0),
        ((model_start + quarter, model_start + quarter * 2), 400.0),
        ((model_start + quarter * 2, model_start + quarter * 3), 600.0),
    ],
    agg=sum_spans(0.0),
    split=no_split,
    label="Capital Expenditures",
)


def cohort_label(cohort: Period) -> str:
    return f"{cohort.end:%Y} Q{((cohort.end.month - 1) // 3) + 1}"


def depreciation_cohort(cohort: Period) -> SpanSeriesDef:
    @span.define(agg=sum_spans(0.0), label=f"Depreciation {cohort_label(cohort)}")
    def DepreciationCohort(ctx: Context) -> Iterable[Span]:
        cohort_capex = CapEx.value(ctx, cohort)

        for index in range(useful_life_qtrs):
            yield Span(cohort.shift(quarter * index), cohort_capex / useful_life_qtrs, split_const)

    return DepreciationCohort


def capex_cohorts() -> Iterable[Period]:
    cohort_period = Period(model_start, model_start + quarter)
    while cohort_period.start < capex_cohort_end:
        yield cohort_period
        cohort_period = cohort_period.shift(quarter)


DepreciationCohorts = [depreciation_cohort(cohort) for cohort in capex_cohorts()]


@span.define(agg=sum_spans(0.0), label="Total Depreciation")
def TotalDepreciation(ctx: Context) -> Iterable[Span]:
    for period in Period.seq(model_start, quarter):
        total: Formula[float | None] = Formula.pure(0.0)
        for cohort in DepreciationCohorts:
            total = total.map2(
                cohort.value(ctx, period), lambda left, right: (left or 0.0) + (right or 0.0)
            )
        yield Span(period, total, no_split)


def main() -> None:
    ctx = Context()
    periods = list(Period.seq(model_start, quarter, date(2027, 12, 31)))
    stmt = Stmt(CapEx, Total(TotalDepreciation, DepreciationCohorts))
    rows = stmt.values(ctx, periods)
    print(fixed_width_table(rows, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))


if __name__ == "__main__":
    main()
