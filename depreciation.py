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
    no_split,
    split_const,
    sum_spans,
)


quarter = relativedelta(months=3, day=31)
model_start = date(2025, 12, 31)
capex_cohort_end = date(2026, 6, 30)
useful_life_qtrs = 4


class CapEx(SpanSeries):
    label = "Capital Expenditures"

    @staticmethod
    def agg(spans: list[Span]) -> float | None:
        return sum_spans(0.0)(spans)

    def spans(self) -> Iterable[Span]:
        yield Span(Period(model_start, model_start + quarter), Formula.pure(400.0), no_split)
        yield Span(
            Period(model_start + quarter, model_start + quarter * 2), Formula.pure(800.0), no_split
        )


class DepreciationCohortBase(SpanSeries):
    cohort: ClassVar[Period]

    @staticmethod
    def agg(spans: list[Span]) -> float | None:
        return sum_spans(0.0)(spans)

    def spans(self) -> Iterable[Span]:
        cohort_capex = self.ctx.get(CapEx).value(self.cohort)

        for index in range(useful_life_qtrs):
            yield Span(
                self.cohort.shift(quarter * index),
                cohort_capex / useful_life_qtrs,
                split_const,
            )


def make_depreciation_cohort_type(cohort: Period) -> type[DepreciationCohortBase]:
    return type(
        f"Depreciation_{cohort.start:%Y_%m}",
        (DepreciationCohortBase,),
        {
            "cohort": cohort,
            "label": f"Depreciation {cohort.end:%Y} Q{((cohort.end.month - 1) // 3) + 1}",
        },
    )


class DepreciationCohorts(SpanSeriesFamily[Period]):
    label = "Depreciation Cohorts"

    def key_label(self, key: Period) -> str:
        cohort = self.ctx.family_series_by_key(self, key)
        if cohort is None:
            return f"{key.end:%Y} Q{((key.end.month - 1) // 3) + 1}"
        return cast(type[SpanSeries], type(cohort)).display_name()

    def spans(self, period: Period) -> SpanFamilyResult[Period]:
        result: dict[Period, tuple[Span, ...]] = {}

        for key in self.active_keys(period):
            cohort_series = self.ctx.get_or_create_family_series(
                self,
                key,
                lambda key=key: make_depreciation_cohort_type(key),
            )
            result[key] = tuple(cohort_series.query(period).eval())

        return result

    def active_keys(self, period: Period) -> Iterable[Period]:
        for cohort_period in capex_cohorts():
            schedule_end = cohort_period.start + quarter * useful_life_qtrs
            if cohort_period.start < period.end and schedule_end > period.start:
                yield cohort_period


class TotalDepreciation(SpanSeries):
    label = "Total Depreciation"
    agg = staticmethod(lambda spans: sum_spans(0.0)(spans))

    def spans(self) -> Iterable[Span]:
        for period in Period.seq(model_start, quarter):
            yield Span(
                period,
                self.ctx.get(DepreciationCohorts)
                .value(period)
                .map(lambda values: sum(v or 0.0 for v in values.values())),
                no_split,
            )


def capex_cohorts() -> Iterable[Period]:
    cohort_period = Period(model_start, model_start + quarter)
    while cohort_period.start < capex_cohort_end:
        yield cohort_period
        cohort_period = cohort_period.shift(quarter)


def main() -> None:
    ctx = Context()
    periods = list(Period.seq(model_start, quarter, date(2027, 12, 31)))
    stmt = Stmt(
        CapEx,
        Total(TotalDepreciation, [DepreciationCohorts]),
    )
    rows = stmt.values(ctx, periods)
    print(fixed_width_table(rows, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))


if __name__ == "__main__":
    main()
