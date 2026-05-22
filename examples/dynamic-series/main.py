from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import ClassVar, cast

from dateutil.relativedelta import relativedelta

from orcaset import (
    Context,
    Formula,
    Period,
    Span,
    SpanFamilyResult,
    SpanSeries,
    SpanSeriesFamily,
    Stmt,
    Total,
    fixed_width_table,
    split_daily,
    sum_spans,
)


# --------------- ASSUMPTIONS ---------------
quarter = relativedelta(months=3, day=31)
model_start = date(2025, 12, 31)
useful_life_qtrs = 4


def qtr_label(period: Period) -> str:
    return f"{period.end:%Y} Q{((period.end.month - 1) // 3) + 1}"


# ------------------ CAPEX ------------------
class CapEx(SpanSeries):
    label = "Capital Expenditures"
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        for period in Period.seq(model_start, quarter):
            yield Span(period, Formula.pure(100.0), split_daily)


# -------- DEPRECIATION COHORT SERIES --------
class DepreciationCohort(SpanSeries):
    cohort: ClassVar[Period]
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        capex = self.ctx.get(CapEx).value(self.cohort)
        depreciation = capex / useful_life_qtrs

        for index in range(useful_life_qtrs):
            yield Span(self.cohort.shift(quarter * index), depreciation, split_daily)


def depreciation_cohort_type(cohort: Period) -> type[DepreciationCohort]:
    return type(
        f"Depreciation_{cohort.end:%Y_%m_%d}",
        (DepreciationCohort,),
        {"cohort": cohort, "label": f"Depreciation {qtr_label(cohort)}"},
    )


# --------- DEPRECIATION SERIES FAMILY ---------
class DepreciationByCohort(SpanSeriesFamily[Period]):
    label = "Depreciation by Cohort"

    def key_label(self, key: Period) -> str:
        return qtr_label(key)

    def spans(self, period: Period) -> SpanFamilyResult[Period]:
        result: dict[Period, tuple[Span, ...]] = {}

        for cohort in active_cohorts(period):
            cohort_series = self.ctx.get_or_create_family_series(
                self,
                cohort,
                lambda cohort=cohort: depreciation_cohort_type(cohort),
            )
            result[cohort] = tuple(cohort_series.query(period).eval())

        return result


class TotalDepreciation(SpanSeries):
    label = "Total Depreciation"
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        for period in Period.seq(model_start, quarter):
            cohort_spans = self.ctx.get(DepreciationByCohort).query(period)
            total = cast(
                Formula[float | None],
                cohort_spans.map(
                    lambda spans_by_cohort: sum_spans(0.0)(
                        [span for spans in spans_by_cohort.values() for span in spans]
                    )
                )
            )
            yield Span(period, total, split_daily)


def capex_cohorts_through(end: date) -> Iterable[Period]:
    cohort = Period(model_start, model_start + quarter)
    while cohort.start < end:
        yield cohort
        cohort = cohort.shift(quarter)


def active_cohorts(period: Period) -> Iterable[Period]:
    for cohort in capex_cohorts_through(period.end):
        schedule_end = cohort.start + quarter * useful_life_qtrs
        if cohort.start < period.end and schedule_end > period.start:
            yield cohort


# ------------- STRUCTURED OUTPUT -------------
def main() -> None:
    ctx = Context()
    stmt = Stmt(
        CapEx,
        Total(TotalDepreciation, [DepreciationByCohort]),
    )

    periods = Period.list(model_start, quarter, date(2027, 12, 31))
    results = stmt.values(ctx, periods)
    print(fixed_width_table(results, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))


if __name__ == "__main__":
    main()
