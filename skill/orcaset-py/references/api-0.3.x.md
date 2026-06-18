# Orcaset Python API Reference

This reference describes the Orcaset 0.3.x def-object API.

## Imports

```py
from datetime import date

from dateutil.relativedelta import relativedelta
from orcaset import (
    Context,
    Formula,
    Group,
    Period,
    Point,
    PointSeriesDef,
    Span,
    SpanAgg,
    SpanSeriesDef,
    Stmt,
    Total,
    avg_spans,
    csv_table,
    fixed_width_table,
    last_span,
    markdown_table,
    no_split,
    point,
    span,
    split_const,
    split_daily,
    sum_spans,
)
```

## Series Definitions

Series are modeled as instances of `SpanSeriesDef` or `PointSeriesDef`. Create series using the decorator or helper constructors, do not instantiate series directly.

```py
type SpanAgg = Callable[[list[Span]], float | None]
type SpanSeriesFn = Callable[[Context], Iterable[Span]]
type PointSeriesFn = Callable[[Context], Iterable[Point]]
type PointInterpolationFn = Callable[[Context, date], Formula[float | None]]

class SpanSeriesDef(NamedTuple):
    fn: SpanSeriesFn
    agg: SpanAgg
    label: str

    def query(self, ctx: Context, period: Period) -> Formula[list[Span]]: ...
    def value(self, ctx: Context, period: Period) -> Formula[float | None]: ...

class PointSeriesDef(NamedTuple):
    fn: PointSeriesFn
    interpolate: PointInterpolationFn
    label: str

    def query(self, ctx: Context, dt: date) -> Point: ...
    def value(self, ctx: Context, dt: date) -> Formula[float | None]: ...
```

Important behavior: Context caches are keyed by object identity. Two equal def values have separate caches if they are different objects.

## Span Series

Use span series for flows and period-based values.

```py
@span.define(agg=sum_spans(0.0), label="Revenue")
def revenue(ctx: Context) -> Iterable[Span]:
    value = 1_000.0
    for period in Period.seq(date(2025, 12, 31), relativedelta(months=1, day=31)):
        yield Span(period, Formula.pure(value), split_daily)
        value *= 1.01
```

Span helper constructors:

```py
span.from_list(values, agg=..., split=no_split, label="Revenue")
span.constant(value, agg=..., split=..., start=..., end=..., label="Units")
span.periodic(start, freq, value, agg=..., split=..., end=..., label="Rent")
span.extend(base)(continuation)  # continuation(ctx, start: date)
span.keyed(keys, series_factory, label="Cohorts")
```

Span operator helpers:

```py
span.neg(series, label=...)
span.scale(series, factor, label=...)
span.add_scalar(series, value, label=...)
span.sub_scalar(series, value, label=...)
span.rsub_scalar(value, series, label=...)
span.div_scalar(series, value, label=...)
span.rdiv_scalar(value, series, label=...)
span.sum([a, b], agg=..., label="Total")
span.sub(a, b, agg=..., label="Difference")
span.mul([a, b], agg=..., label="Product")
span.div(a, b, agg=..., label="Ratio")
```

Aggregation and splitting:

- `sum_spans(fill)` sums queried spans and substitutes `fill` for `None`.
- `avg_spans(yf, fill)` computes a year-fraction weighted average.
- `last_span(fill)` returns the last queried span value.
- `split_daily` prorates by days, `split_const` keeps both sides unchanged, and `no_split` raises if a span must be split.
- `span.constant(...)` and `span.periodic(...)` require an explicit `split=...`.
- `span.extend(...)` passes the concrete base series end date to the continuation and does not call the continuation if the base yields no spans.

## Point Series

Use point series for balances and point-in-time metrics.

```py
def cash_value(ctx: Context, dt: date) -> Formula[float | None]:
    if dt < model_start:
        return Formula.pure(None)
    if dt == model_start:
        return Formula.pure(1_000.0)
    return Formula.pure(1_000.0) + net_cash_flow.value(ctx, Period(model_start, dt))


@point.define(interpolate=cash_value, label="Cash")
def cash(_: Context) -> Iterable[Point]:
    yield Point(model_start, Formula.pure(1_000.0))
```

Point helper constructors:

```py
point.from_list([(dt, value)], label="History")
point.constant(value, start=start, end=end, label="Constant")
point.derived(interpolate, label="Metric")
point.accumulate(start, value, changes, label="Cash")
point.keyed(keys, series_factory, label="Tranches")
```

Point operator helpers:

```py
point.neg(series, label=...)
point.scale(series, factor, label=...)
point.add_scalar(series, value, label=...)
point.sub_scalar(series, value, label=...)
point.rsub_scalar(value, series, label=...)
point.div_scalar(series, value, label=...)
point.rdiv_scalar(value, series, label=...)
point.sum([a, b], label="Total assets")
point.sub(a, b, label="Check")
point.mul([a, b], label="Product")
point.div(a, b, label="Ratio")
```

`point.accumulate(start, value, changes, label=...)` returns `None` before
`start`, returns the starting value at `start`, and adds non-`None` span changes
between `start` and each queried date.

## Querying And Evaluation

Use one `Context` per model run or scenario.

```py
ctx = Context()
period = Period(date(2026, 1, 1), date(2026, 4, 1))
dt = date(2026, 4, 1)

spans = revenue.query(ctx, period).eval()
revenue_value = revenue.value(ctx, period).eval()

cash_cell = cash.query(ctx, dt)
cash_value = cash.value(ctx, dt).eval()
graph = ctx.deps(cash_cell)
```

`SpanSeriesDef.query(...)` returns `Formula[list[Span]]` because span queries may
materialize, clip, split, and gap-fill spans lazily. `SpanSeriesDef.value(...)`
aggregates the queried spans with the def's `agg`.

`PointSeriesDef.query(...)` returns the date-specific `Point` cell directly.
`PointSeriesDef.value(...)` returns a formula for that point's value.

For dynamic formula collections, keep dependencies in the formula graph:

```py
values = [line.value(ctx, period) for line in lines]
total = Formula.sequence(values).map(lambda vals: sum(value or 0.0 for value in vals))
```

## Linked And Recursive Formulas

Use explicit `ctx` queries inside formulas so dependencies remain visible:

```py
@span.define(agg=sum_spans(0.0), label="Interest")
def interest(ctx: Context) -> Iterable[Span]:
    for period in Period.seq(model_start, relativedelta(months=3, day=31)):
        beginning_debt = debt.value(ctx, period.start)
        yield Span(period, beginning_debt * rate / 4, split_daily)

debt = point.accumulate(model_start, opening_debt, interest, label="Debt")
```

## Multi-File Circular Dependencies

Use top-level imports for acyclic dependencies. For cross-file circular dependencies inside
`@span.define(...)` functions or point source/interpolation functions, use local imports inside
the smallest series function that needs the dependency:

```py
# interest.py
@span.define(agg=sum_spans(0.0), label="Interest")
def interest(ctx: Context) -> Iterable[Span]:
    from .debt import debt

    for period in Period.seq(start_date, quarter):
        beginning_debt = debt.value(ctx, period.start)
        yield Span(period, beginning_debt * interest_rate / 4, split_daily)
```

For cross-file circular dependencies passed to convenience constructors, pass a
zero-argument ref function instead of importing the dependency at module load time:

```py
# debt.py
from orcaset import SpanSeriesDef, point

from .assumptions import initial_debt, start_date


def interest_ref() -> SpanSeriesDef:
    from .interest import interest

    return interest


debt = point.accumulate(start_date, initial_debt, interest_ref, label="Debt")
```

Use the same ref pattern for helper lists:

```py
total_cash_flow = span.sum(
    [operating_cash_flow, financing_ref],
    agg=sum_spans(0.0),
    label="Total cash flow",
)
```

Use a lambda only when the referenced series is already in scope. A lambda cannot contain an
import statement, so named ref functions are clearer for cross-file dependencies.

For self-references to prior periods, query the prior period explicitly:

```py
prior = revenue.query(ctx, period.from_start(relativedelta(months=-1)))
yield Span(period, prior.map(lambda spans: sum(s.eval(ctx) or 0.0 for s in spans) + 100.0), no_split)
```

Avoid same-period circular formulas unless convergence is intentional and tested.
When cyclic cells are solved, newly resolving cells are initially primed with `1.0`.

## Dynamic Keyed Series

Use keyed collections for rows whose keys depend on a queried period or date.
The keyed collection caches per-key series definitions inside each `Context`.

Span keyed collections:

```py
def cohort_keys(period: Period) -> Iterable[Period]:
    return Period.seq(model_start, qtr_offset, period.end)

def create_cohort_series(cohort: Period) -> SpanSeriesDef:
    @span.define(agg=sum_spans(0.0), label=f"Qtr {cohort.end:%Y-%m-%d}")
    def depreciation_cohort(ctx: Context) -> Iterable[Span]:
        capex_value = capex.value(ctx, cohort)
        for period in Period.list(cohort.end, qtr_offset, cohort.end + qtr_offset * 4):
            yield Span(period, capex_value / 4, split_daily)

    return depreciation_cohort

depreciation_cohorts = span.keyed(
    keys=cohort_keys,
    series=create_cohort_series,
    label="Depreciation Cohorts",
)
```

Point keyed collections:

```py
def tranche_keys(dt: date) -> Iterable[str]:
    return active_tranches_as_of(dt)

def create_tranche(key: str) -> PointSeriesDef:
    @point.derived(label=f"Tranche {key}")
    def tranche(ctx: Context, dt: date) -> Formula[float | None]:
        return Formula.pure(tranche_balance(key, dt))

    return tranche

tranches = point.keyed(tranche_keys, create_tranche, label="Tranches")
```

Keyed collection methods:

```py
cohorts.keys(period)          # stable, de-duplicated tuple of keys
cohorts.get(ctx, key)         # context-cached SpanSeriesDef or PointSeriesDef
cohorts.items(ctx, period)    # tuple[(key, SpanSeriesDef), ...]
tranches.items(ctx, dt)       # tuple[(key, PointSeriesDef), ...]
```

`span.keyed(...)` can render only in period statements. `point.keyed(...)` can
render in period statements and date statements.

## Statements

```py
stmt = Stmt(
    Group([
        Total(net_income, [
            Total(ebit, [revenue, costs, depreciation]),
            taxes,
        ]),
        Total(cash_flow, [net_income, depreciation_add_back, capex]),
        Total(total_assets, [cash, ppe_net]),
    ])
)

periods = Period.list(model_start, relativedelta(months=3, day=31), model_end)
result = stmt.values(ctx, periods)
print(fixed_width_table(result))
```

Statement APIs:

```py
Stmt(*items)
Group([items])
Total(series, [items])
stmt.values(ctx, periods)              # alias for values_for_periods
stmt.values_for_periods(ctx, periods)  # span rows use periods; point rows use boundaries
stmt.values_for_dates(ctx, dates)      # point rows use dates; span rows return None
```

Statement rows use `series.label`. Period statements evaluate point series at
the sorted unique period boundaries. Keyed rows expand to a `GroupRow` whose
children are the key-specific series rows.

Formatters:

```py
fixed_width_table(result, date_formatter=..., value_formatter=...)
csv_table(result, date_formatter=..., value_formatter=...)
markdown_table(result, date_formatter=..., value_formatter=...)
```

## Historical Plus Projection

Use `span.from_list(...)` for historicals, then extend with projections:

```py
historical_revenue = span.from_list(
    [((date(2023, 12, 31), date(2024, 12, 31)), 350_018.0)],
    agg=sum_spans(0.0),
    split=split_daily,
    label="Revenue",
)

@span.extend(historical_revenue)
def revenue(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, relativedelta(years=1)):
        prior = revenue.value(ctx, period.from_start(relativedelta(years=-1)))
        yield Span(period, prior * 1.05, split_daily)
```

`span.extend(base)` inherits `base.agg` and labels the result with the
continuation function name.

## Dependency Inspection

Inspect dependencies from concrete cells, not from series defs:

```py
ctx = Context()
cell = cash.query(ctx, date(2026, 12, 31))
cell.eval(ctx)
graph = ctx.deps(cell)
dot = graph.to_dot()
```

Span dependencies use concrete spans from `series.query(ctx, period).eval()`.

## Pitfalls

- Do not mutate labels after construction; pass `label=` when creating the def.
- Do not use arithmetic operators on series defs; use `span.*` or `point.*` helpers.
- Do not evaluate formulas too early when building dependent formulas. Return `Formula[...]` objects from model functions.
- Do not fetch network or filesystem data during formula evaluation. Load external data before defining or querying model series.
- Do not structure statements as flat lists of line items. Use groups and totals to structure statements.
- Do not define model end dates. Query ranges are a reporting concern and should be defined in output code, never in the model.
