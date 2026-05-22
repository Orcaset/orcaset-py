from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import ClassVar

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


# --------- DEPRECIATION SERIES FAMILY ---------
class DepreciationByCohort(SpanSeriesFamily[Period]):
    label = "Depreciation by Cohort"

    def key_label(self, key: Period) -> str:
        return f"{key.end:%Y} Q{((key.end.month - 1) // 3) + 1}"

    def spans(self, period: Period) -> SpanFamilyResult[Period]:
        """Return a dictionary of `{Period: list[Span]}` for the query period."""
        result: dict[Period, tuple[Span, ...]] = {}

        # Iterate over active keys for the period
        for cohort in self.active_keys(period):
            # Get or create the cohort series for the key
            cohort_series = self.ctx.get_or_create_family_series(
                family=self,
                key=cohort,
                factory=lambda cohort=cohort: self.create_cohort_type(cohort),
            )
            # Query the cohort series for the period and add the spans to the result
            result[cohort] = tuple(cohort_series.query(period).eval())

        return result

    def active_keys(self, period: Period) -> Iterable[Period]:
        """Return periods starting before the end of the query period."""
        for cohort_key in Period.seq(model_start, quarter):
            if cohort_key.start < period.end:
                yield cohort_key
            else:
                return

    def create_cohort_type(self, cohort: Period) -> type[DepreciationCohort]:
        """Factory method to create a new `DepreciationCohort` subclass for the given cohort."""
        return type(
            f"Depreciation_{cohort.end:%Y_%m_%d}",
            (DepreciationCohort,),
            {
                "cohort": cohort,
                "label": f"Depreciation {cohort.end:%Y} Q{((cohort.end.month - 1) // 3) + 1}",
            },
        )


class TotalDepreciation(SpanSeries):
    label = "Total Depreciation"
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        for period in Period.seq(model_start, quarter):
            cohort_spans = self.ctx.get(DepreciationByCohort).value(period)
            total: Formula[float | None] = cohort_spans.map(
                lambda spans_by_cohort: sum([v or 0.0 for v in spans_by_cohort.values()]),
            )
            yield Span(period, total, split_daily)


# ------------- STRUCTURED OUTPUT -------------
ctx = Context()
stmt = Stmt(
    CapEx,
    Total(TotalDepreciation, [DepreciationByCohort]),
)

periods = Period.list(model_start, quarter, date(2027, 12, 31))
results = stmt.values(ctx, periods)
print(fixed_width_table(results, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))

# Start                                 2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30
# End                       2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30  2027-12-31
# Capital Expenditures                      100.00      100.00      100.00      100.00      100.00      100.00      100.00      100.00
#   Depreciation by Cohort
#     2026 Q1                                25.00       25.00       25.00       25.00        0.00        0.00        0.00        0.00
#     2026 Q2                                            25.00       25.00       25.00       25.00        0.00        0.00        0.00
#     2026 Q3                                                        25.00       25.00       25.00       25.00        0.00        0.00
#     2026 Q4                                                                    25.00       25.00       25.00       25.00        0.00
#     2027 Q1                                                                                25.00       25.00       25.00       25.00
#     2027 Q2                                                                                            25.00       25.00       25.00
#     2027 Q3                                                                                                        25.00       25.00
#     2027 Q4                                                                                                                    25.00
# ------------------------------------------------------------------------------------------------------------------------------------
# Total Depreciation                         25.00       50.00       75.00      100.00      100.00      100.00      100.00      100.00
