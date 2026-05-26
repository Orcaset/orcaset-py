# Dynamic Series Example

*Run from the repo root: `uv run python examples/dynamic-series/main.py`. Code: [main.py](./main.py).*

This example walks through dynamic series generation by building a simple depreciation schedule.

Sometimes a model don't know what series it needs until it's queried. A detailed depreciation schedule is a good example. The schedule detail should have one series per capital expenditure cohort (depreciation for Q1 2026 capex, Q2 2026 capex, etc.), but the set of required cohorts depends on the query period. The same pattern applies customer retention, revenue by cohort, and similar schedules.

This example model has three components: capital expenditures, depreciation detail by cohort, and total depreciation expense.

## Capital expenditures

The capex series simply returns `100.0` every quarter, indefinitely.

```py
quarter = relativedelta(months=3, day=31)
model_start = date(2025, 12, 31)

CapEx = span.periodic(
    model_start,
    quarter,
    100.0,
    agg=sum_spans(0.0),
    split=split_daily,
    name="Capital Expenditures",
)
```

## Depreciation detail by cohort

The model will generate one series for each depreciation cohort. These will be ordinary `SpanSeries`. The template class below will be the base for the dynamically created schedule detail lines. It queries capex for a specific cohort period and spreads expenditures evenly over the following four quarters.

```py
useful_life_qtrs = 4

class DepreciationCohort(SpanSeries):
    cohort: ClassVar[Period]
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        capex = self.ctx.get(CapEx).value(self.cohort)
        depreciation = capex / useful_life_qtrs

        for index in range(useful_life_qtrs):
            yield Span(self.cohort.shift(quarter * index), depreciation, split_daily)
```

Note that `cohort` is a `ClassVar`. Generated subclasses will define this variable with a concrete period.

## Series Family

A `SpanSeriesFamily` is a series-of-series. Where a `SpanSeries` produces spans, a family produces a keyed collection of span groups, lazily instantiating a backing `SpanSeries` subclass for each new key it encounters.

A subclass needs three things:

1. A `spans(period)` method that returns one collection of spans per active key.
2. A way to enumerate the active keys for a query period.
3. A factory that produces a new `SpanSeries` subclass per key.

We'll start with a stub showing only `spans`, then fill in the helpers.

```py
class DepreciationByCohort(SpanSeriesFamily[Period]):

    def spans(self, period: Period) -> SpanFamilyResult[Period]:
        """Return a `{cohort: spans}` mapping for the query period."""
        result: dict[Period, tuple[Span, ...]] = {}

        for cohort in self.active_keys(period):
            cohort_series = self.ctx.get_or_create_family_series(
                family=self,
                key=cohort,
                factory=lambda cohort=cohort: self.create_cohort_type(cohort),
            )
            result[cohort] = tuple(cohort_series.query(period).eval())

        return result
```

Breaking down the three calls inside the loop:

* `active_keys(period)` returns the cohort keys applicable to the query period (defined below).
* `get_or_create_family_series(...)` looks up a cached series type for `(family, key)`. If none exists, it calls `factory()` to build one, caches it, and returns the corresponding instance from the context.
* `cohort_series.query(period).eval()` returns the cohort's spans over the requested period.

The `factory=lambda cohort=cohort: ...` default-argument trick captures the current `cohort` value rather than late-binding the loop variable. It's a standard Python idiom when building closures inside a loop.

Next, the helpers:

```py
    def active_keys(self, period: Period) -> Iterable[Period]:
        """Yield cohort periods that start before the query period ends."""
        for cohort_key in Period.seq(model_start, quarter):
            if cohort_key.start < period.end:
                yield cohort_key
            else:
                return

    def create_cohort_type(self, cohort: Period) -> type[DepreciationCohort]:
        """Build a `DepreciationCohort` subclass for a single cohort."""
        return type(
            f"Depreciation_{cohort.end:%Y_%m_%d}",
            (DepreciationCohort,),
            {
                "cohort": cohort,
                "label": f"Depreciation {cohort.end:%Y} Q{((cohort.end.month - 1) // 3) + 1}",
            },
        )
```

This is the core pattern: the family is query-aware, while each generated member remains a normal series.

Finally, add labels for the family and its keys:

```py
class DepreciationByCohort(SpanSeriesFamily[Period]):
    label = "Depreciation by Cohort"

    def key_label(self, key: Period) -> str:
        return f"{key.end:%Y} Q{((key.end.month - 1) // 3) + 1}"

    # ...
```

## Total depreciation

The total depreciation series consumes the family values for each quarter and sums the currently active cohorts.

```py
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
```

Reading from a family looks like reading from an ordinary series, except the response is a `{key: spans}` mapping instead of a flat list.

The summing happens *inside* `Formula.map` rather than against `cohort_spans` directly. `cohort_spans` is a `Formula[Mapping[K, ...]]`, not the resolved values — `.map` defers the sum until the formula is evaluated, which is what lets the family populate its cohort values lazily.

## Structured output

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
    2026 Q1                                25.00       25.00       25.00       25.00        0.00        0.00        0.00        0.00
    2026 Q2                                            25.00       25.00       25.00       25.00        0.00        0.00        0.00
    2026 Q3                                                        25.00       25.00       25.00       25.00        0.00        0.00
    2026 Q4                                                                    25.00       25.00       25.00       25.00        0.00
    2027 Q1                                                                                25.00       25.00       25.00       25.00
    2027 Q2                                                                                            25.00       25.00       25.00
    2027 Q3                                                                                                        25.00       25.00
    2027 Q4                                                                                                                    25.00
------------------------------------------------------------------------------------------------------------------------------------
Total Depreciation                         25.00       50.00       75.00      100.00      100.00      100.00      100.00      100.00
```

## Limitations

Series can only be dynamic with respect to dates and periods, not values. You cannot create a series based on the value of some cell. The practical workaround is to define every series that might be needed and conditionally populate its cells with non-null values when the trigger is met.

The backing series within a family are generally opaque to outside code. You can access cells or values by series key, but treat the family as the public interface rather than reaching through it to manipulate the generated series directly.
