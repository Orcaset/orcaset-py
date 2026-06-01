# Dynamic Series

This example builds a depreciation schedule by creating one `SpanSeriesDef` per capex cohort.

Dynamic series are ordinary def objects. Creating a new def object gives it distinct identity and separate context caches, even if it has the same label or function shape as another def.

```py
def depreciation_cohort(cohort: Period) -> SpanSeriesDef:
    @span.define(agg=sum_spans(0.0), label=f"Depreciation {quarter_label(cohort)}")
    def DepreciationCohort(ctx: Context) -> Iterable[Span]:
        capex = CapEx.value(ctx, cohort)
        depreciation = capex / useful_life_qtrs

        for index in range(useful_life_qtrs):
            yield Span(cohort.shift(quarter * index), depreciation, split_daily)

    return DepreciationCohort
```

The statement renders total depreciation with each generated cohort line as children:

```py
cohorts = Period.list(model_start, quarter, model_end)
DepreciationCohorts = [depreciation_cohort(cohort) for cohort in cohorts]

stmt = Stmt(
    CapEx,
    Total(TotalDepreciation, DepreciationCohorts),
)
```

Run the example:

```sh
uv run python examples/dynamic-series/main.py
```
