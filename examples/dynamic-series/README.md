# Dynamic Series Example

*Run from the repo root: `uv run python examples/dynamic-series/main.py`. Code: [main.py](./main.py).*

This example walks through dynamic series by building a simple depreciation schedule. Orcaset does not limit series bounds: a series can be infinite, and users can query it over arbitrary dates. Sometimes that means the line items required for a statement are not known ahead of query time and must be built dynamically in response to the query.

A depreciation schedule is a good example. Users often want to see depreciation by cohort, but the number of visible cohorts depends on the queried date range. The same idea applies to similar schedules, such as customer retention or revenue by cohort.

## Setup

The model starts with one infinite CapEx series. It creates one span per calendar quarter, starting on `2025-12-31`, with `100.0` of capital expenditures in each quarter.

```py
quarter = relativedelta(months=3, day=31)
model_start = date(2025, 12, 31)
useful_life_qtrs = 4


class CapEx(SpanSeries):
    label = "Capital Expenditures"
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        for period in Period.seq(model_start, quarter):
            yield Span(period, Formula.pure(100.0), split_daily)
```

`Period.seq(...)` has no end date here, so `CapEx` can keep producing quarterly spans as far as the query requires.

## Cohort Series

Each depreciation cohort is still an ordinary `SpanSeries`. The class below expects a `cohort` period, reads the CapEx value for that period, and spreads it across four quarters.

```py
class DepreciationCohort(SpanSeries):
    cohort: ClassVar[Period]
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        capex = self.ctx.get(CapEx).value(self.cohort)
        depreciation = capex / useful_life_qtrs

        for index in range(useful_life_qtrs):
            yield Span(self.cohort.shift(quarter * index), depreciation, split_daily)
```

The important detail is that `cohort` is a class attribute. Each generated cohort type gets its own `cohort` value and can be cached like any other series type.

```py
def depreciation_cohort_type(cohort: Period) -> type[DepreciationCohort]:
    return type(
        f"Depreciation_{cohort.end:%Y_%m_%d}",
        (DepreciationCohort,),
        {"cohort": cohort, "label": f"Depreciation {qtr_label(cohort)}"},
    )
```

## Series Family

`SpanSeriesFamily` is the dynamic layer. Instead of defining all possible cohorts up front, the family receives the query period, decides which cohort keys are active for that period, creates any missing backing series, and returns the queried spans by key.

```py
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
```

Breaking this down:

* `active_cohorts(period)` returns only cohorts with depreciation that overlaps the query period.
* `get_or_create_family_series(...)` registers a generated `SpanSeries` type for the family key.
* `cohort_series.query(period).eval()` returns the cohort spans relevant to the requested period.
* `key_label(...)` controls how the generated rows are labeled in statement output.

This is the core pattern: the family is query-aware, while each generated member remains a normal series.

## Total Depreciation

The total line item can consume the family values for each quarter and sum the currently active cohorts.

```py
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
```

`DepreciationByCohort.query(period)` resolves to a mapping of `{cohort_key: spans}` for the query period. The total series flattens those spans and lets `sum_spans(0.0)` aggregate them into one scalar span value.

## Structured Output

Statements can include families directly. The formatter expands the family into one row per key that appears in the queried periods.

```py
ctx = Context()
stmt = Stmt(
    CapEx,
    Total(TotalDepreciation, [DepreciationByCohort]),
)

periods = Period.list(model_start, quarter, date(2027, 12, 31))
results = stmt.values(ctx, periods)
print(fixed_width_table(results, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))
```

The first eight quarters produce:

```text
Start                                 2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30
End                       2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30  2027-12-31
Capital Expenditures                      100.00      100.00      100.00      100.00      100.00      100.00      100.00      100.00
  Depreciation by Cohort
    2026 Q1                                25.00       25.00       25.00       25.00
    2026 Q2                                            25.00       25.00       25.00       25.00
    2026 Q3                                                        25.00       25.00       25.00       25.00
    2026 Q4                                                                    25.00       25.00       25.00       25.00
    2027 Q1                                                                                25.00       25.00       25.00       25.00
    2027 Q2                                                                                            25.00       25.00       25.00
    2027 Q3                                                                                                        25.00       25.00
    2027 Q4                                                                                                                    25.00
------------------------------------------------------------------------------------------------------------------------------------
Total Depreciation                         25.00       50.00       75.00      100.00      100.00      100.00      100.00      100.00
```

## Limitations and Gotchas

Series can only be dynamic with respect to dates and periods, not values. For example, you cannot dynamically create a series based on the value of some cell. A practical workaround is to create any series that may be needed, but only populate cells in those series with non-null values when the trigger is met.

The actual underlying series within a family are generally opaque to outside series. You can access structured cells or values by series key, but outside code should treat the family as the public interface rather than reaching through it to manipulate the generated backing series directly.
