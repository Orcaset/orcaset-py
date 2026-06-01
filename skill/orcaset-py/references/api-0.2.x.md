# Orcaset Python API Reference

This reference describes the current def-object API.

## Imports

```py
from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta
from orcaset import (
    Context,
    Formula,
    Period,
    Point,
    PointSeriesDef,
    Span,
    SpanAgg,
    SpanSeriesDef,
    Stmt,
    Group,
    Total,
    fixed_width_table,
    point,
    span,
    split_daily,
    sum_spans,
)
```

## Series Definitions

Series are immutable named tuple definition objects. They are not classes and do not need `ctx.get(...)`.

```py
type SpanAgg = Callable[[list[Span]], float | None]
type SpanSeriesFn = Callable[[Context], Iterable[Span]]
type PointSeriesFn = Callable[[Context, date], Formula[float | None]]

class SpanSeriesDef(NamedTuple):
    fn: SpanSeriesFn
    agg: SpanAgg
    label: str

    def query(self, ctx: Context, period: Period) -> Formula[list[Span]]: ...
    def value(self, ctx: Context, period: Period) -> Formula[float | None]: ...

class PointSeriesDef(NamedTuple):
    fn: PointSeriesFn
    label: str

    def query(self, ctx: Context, dt: date) -> Point: ...
    def value(self, ctx: Context, dt: date) -> Formula[float | None]: ...
```

## Span Series

Use span series for flows and period-based values.

```py
@span.define(agg=sum_spans(0.0), label="Revenue")
def Revenue(ctx: Context) -> Iterable[Span]:
    value = 100.0
    for period in Period.seq(date(2025, 12, 31), relativedelta(months=1, day=31)):
        yield Span(period, Formula.pure(value), split_daily)
        value *= 1.01
```

Helpers:

```py
span.from_list(values, agg=..., split=split_daily, label="Revenue")
span.constant(value, agg=..., split=split_daily, start=..., end=..., label="Units")
span.periodic(start, freq, value, agg=..., split=split_daily, end=..., label="Rent")
span.extend(base)(continuation)
span.sum([a, b], agg=..., label="Total")
span.sub(a, b, agg=..., label="Difference")
span.mul([a, b], agg=..., label="Product")
span.div(a, b, agg=..., label="Ratio")
span.scale(a, factor, label="Scaled")
```

Use helper functions rather than arithmetic operators on series defs; defs are named tuples.

## Point Series

Use point series for balances and point-in-time metrics.

```py
@point.define(label="Cash")
def Cash(ctx: Context, dt: date) -> Formula[float | None]:
    if dt < model_start:
        return Formula.pure(None)
    if dt == model_start:
        return Formula.pure(1000.0)
    return Formula.pure(1000.0) + NetCashFlow.value(ctx, Period(model_start, dt))
```

Helpers:

```py
point.accumulate(start, value, changes, label="Cash")
point.sum([a, b], label="Total assets")
point.sub(a, b, label="Check")
point.mul([a, b], label="Product")
point.div(a, b, label="Ratio")
point.scale(a, factor, label="Scaled")
```

Use helper functions rather than arithmetic operators on series defs; defs are named tuples.

## Querying And Evaluation

Use one `Context` per model run or scenario.

```py
ctx = Context()
period = Period(date(2026, 1, 1), date(2026, 4, 1))
dt = date(2026, 4, 1)

spans = Revenue.query(ctx, period).eval()
revenue_value = Revenue.value(ctx, period).eval()

cash_cell = Cash.query(ctx, dt)
cash_value = Cash.value(ctx, dt).eval()
graph = ctx.deps(cash_cell)
```

`SpanSeriesDef.query(...)` returns `Formula[list[Span]]` because span queries may lazily materialize, clip, interpolate, and gap-fill spans. `PointSeriesDef.query(...)` returns `Point` directly because it is the date-specific cell handle.

## Statements

```py
stmt = Stmt(
    Group([
        Total(NetIncome, [Revenue, Costs, Taxes]),
        Cash,
    ])
)

periods = Period.list(model_start, relativedelta(months=3, day=31), model_end)
result = stmt.values(ctx, periods)
print(fixed_width_table(result))
```

Statement rows use `series.label`. `Total(series, children)` nests child rows and renders a horizontal rule before the total.

## Dynamic Lines

Create dynamic model lines by creating def objects dynamically and storing them in a list or mapping. Each def object has distinct identity and separate context caches.

```py
def cohort_line(cohort: Period) -> SpanSeriesDef:
    @span.define(agg=sum_spans(0.0), label=f"Depreciation {cohort.end:%Y-%m-%d}")
    def DepreciationCohort(ctx: Context) -> Iterable[Span]:
        capex = CapEx.value(ctx, cohort)
        for index in range(4):
            yield Span(cohort.shift(relativedelta(months=3) * index), capex / 4, split_daily)

    return DepreciationCohort

cohort_lines = [cohort_line(cohort) for cohort in cohorts]
```

## Pitfalls

- Do not call `ctx.get(...)`; series defs are queried directly.
- Do not mutate labels after construction; pass `label=` to decorators and helpers.
- Avoid network or filesystem side effects during formula evaluation. Load external data before defining the model series.
- Use `Span.query(ctx, period).eval()` for raw cells and `Span.value(ctx, period).eval()` for aggregated values.
