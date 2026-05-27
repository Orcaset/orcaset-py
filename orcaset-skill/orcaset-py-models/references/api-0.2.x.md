# Orcaset Python API Reference: 0.2.0

Use this reference only when the detected Orcaset version is `0.2.x`, or when local source inspection confirms these signatures still match.

## Contents

- Imports
- Periods
- Formulas and Cells
- SpanSeries
- PointSeries
- Context and Resolution
- Statement Views
- Historical Actuals Plus Projections
- Dynamic Series Families
- Debugging Dependencies
- Version-Specific Pitfalls

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
    PointFamilyResult,
    PointSeries,
    PointSeriesFamily,
    Span,
    SpanFamilyResult,
    SpanSeries,
    SpanSeriesFamily,
    Stmt,
    Total,
    YF,
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

## Periods

- `Period(start, end)`: raises and error if `start` is not strictly before `end`

Key functions:

```py
Period.seq(cls, start: date, freq: relativedelta, end: date | None = None) -> Generator[Period, None, None]:
    """Generator over a (possibly infinite) sequence of sequential, increasing periods."""
    # Example usage creating an infinite series:
    # for period in Period.seq(model_start, month):
    #   ...

Period.list(cls, start: date, freq: relativedelta, end: date) -> list[Period]:
    """Create a list of sequential, increasing periods."""

Period.from_end(self, offset: relativedelta) -> Period:
    """New period with dates `end` and `end + offset`."""
    # E.g get next period with `period.from_end(relativedelta(months=3, day=31))

Period.from_start(self, offset: relativedelta) -> Period:
    """New period with dates `start` and `start + offset`."""
    # E.g get trailing period with `period.from_start(relativedelta(months=-1))

Period.shift(self, offset: relativedelta) -> Period:
    """New period by shifting both start and end dates by `offset`."""
    # Good for creating year-ago reference. E.g. `period.shift(relativedelta(years=-1))`
```

Month-end models usually use `relativedelta(..., day=31)` so generated periods preserve month ends.

## Formulas and Cells

Cells hold `Formula[float | None]` values for lazy value and dependency resolution.

```py
span_cell = Span(period=Period(date(2026, 1, 1), date(2026, 2, 1)), fn=Formula.pure(100.0), split=split_daily)
point_cell = Point(date=date(2026, 1, 31), fn=Formula.pure(42.0))
```

`Span` values must have a `split` function in the form `Callable[[Span, date], tuple[SpanFormulaTransform, SpanFormulaTransform]]` used to interpolate partial periods. Built-in functions include:

- `no_split`: Raises an exception on splitting (useful if split logic is undefined).
- `daily_split`: Left and right prorated by proportion of days.
- `split_const`: Left and right both resolve to parent span's value (usefull for spans that represent levels).

Formula arithmetic is overloaded and propagates `None`:

```py
interest = self.ctx.get(Debt).value(period.start) * annual_rate / 12
```

## SpanSeries

Use `SpanSeries` for values over time. Every span series needs an aggregation function.

- Flows: Typically `def sum_spans(fill: float) -> SpanAggregator:` for accruals or flows over time.
- Levels: Typically `def avg_spans(yf: Callable[[date, date], float], fill: float) -> SpanAggregator: ...` for levels over time.


```py
class Revenue(SpanSeries):
    agg = sum_spans(0.0)
    label = "Revenue"

    def spans(self) -> Iterable[Span]:
        for period in Period.seq(model_start, month):
            yield Span(period, Formula.pure(100.0), split_daily)
```

Decorator form:

```py
@span.define(agg=sum_spans(0.0))
def Revenue(self: SpanSeries) -> Iterable[Span]:
    for period in Period.seq(model_start, month):
        yield Span(period, Formula.pure(100.0), split_daily)
```

Common constructors and operators:

```py
# E.g. Historicals
RevenueActuals = span.from_list(
    [((date(2025, 1, 1), date(2025, 12, 31)), 1_000.0)],
    agg=sum_spans(0.0),
    split=split_daily,
    name="Revenue actuals",
)

# Constant value per period
OperatingExpenses = span.periodic(
    model_start,
    month,
    -200.0,
    agg=sum_spans(0.0),
    split=split_daily,
    name="Operating expenses",
)

CostOfRevenue = span.scale(Revenue, -0.30, name="Cost of revenue")
GrossProfit = span.sum([Revenue, CostOfRevenue], agg=sum_spans(0.0), name="Gross profit")
Taxes = EBIT * -0.20
```

## PointSeries

Use `PointSeries` for balance sheet lines and point-in-time metrics.

```py
@point.define
def CommonStock(self: PointSeries, dt: date) -> Formula[float | None]:
    lable = "Common stock"

    if dt < model_start:
        return Formula.pure(None)
    return Formula.pure(common_stock_value)
```

Use `point.accumulate` for roll-forwards driven by a span series:

```py
Cash = point.accumulate(model_start, initial_cash, TotalCashFlow, name="Cash")
PpeNet = point.accumulate(model_start, initial_ppe_net, PpeNetChange, name="PPE net")
TotalAssets = point.sum([Cash, PpeNet], name="Total assets")
BalanceSheetCheck = point.sub(TotalAssets, TotalEquityAndLiabilities, name="Balance sheet check")
```

Point operators include `point.sum`, `point.sub`, `point.mul`, `point.div`, `point.scale`, and scalar arithmetic through the series type.

## Context and Resolution

`Context` owns series instances, caches cells, resolves formulas, and tracks dependencies.

```py
ctx = Context()
revenue = ctx.get(Revenue)

spans = revenue.query(Period(date(2026, 1, 1), date(2026, 4, 1))).eval()  # Evaluates to `list[Span]`
value = revenue.value(Period(date(2026, 1, 1), date(2026, 4, 1))).eval()  # Evaluates to `float | None`
cash = ctx.get(Cash).value(date(2026, 4, 1)).eval()  # Evaluates to `float | None`
```

Use `.query(...)` when raw cells or clipped spans/points are needed. Use `.value(...)` when the resolved numeric value is needed. Use one `Context` per model run or scenario.

Do not instantiate series classes directly. Use `ctx.get(SeriesType)`.

## Statement Views

`Stmt`, `Group`, and `Total` define output views. They do not define the model.

```py
income_stmt = Group([
    Total(NetIncome, [
        Total(EBIT, [
            Total(GrossProfit, [Revenue, CostOfRevenue]),
            OperatingExpenses,
            Depreciation,
        ]),
        IncomeTax,
    ])
])

stmt = Stmt(income_stmt, balance_sheet_stmt)

ctx = Context()
periods = Period.list(model_start, month, date(2026, 6, 30))
result = stmt.values(ctx, periods)
print(fixed_width_table(result, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))
```

For date-based point output, use `stmt.values_for_dates(ctx, dates)`. For period output, use `stmt.values(ctx, periods)` or `stmt.values_for_periods(ctx, periods)`.

Formatters include `fixed_width_table`, `markdown_table`, and `csv_table`. Row names will use the `Series.label` value or the class name if no label exits.

## Historical Actuals Plus Projections

Use `span.extend` when a line has actuals followed by projections.

```py
HistoricalRevenue = span.from_list(
    [
        ((date(2024, 12, 31), date(2025, 12, 31)), 1_000.0),
    ],
    agg=sum_spans(0.0),
    split=split_daily,
    name="Historical revenue",
)

@span.extend(HistoricalRevenue)
def Revenue(self: SpanSeries, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, relativedelta(years=1, day=31)):
        prior_period = period.shift(relativedelta(years=-1))
        prior = self.ctx.get(Revenue).value(prior_period)
        yield Span(period, prior * (1 + revenue_growth_rate), split_daily)
```

`span.extend` inherits the base series aggregation function and passes the last historical span end date as `start`.

## Dynamic Series Families

Use families for cohort schedules, vintages, tranches, or other dynamic row sets.

```py
class DepreciationCohort(SpanSeries):
    cohort: ClassVar[Period]
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        capex = self.ctx.get(CapitalExpenditures).value(self.cohort)
        depreciation = capex / useful_life_quarters
        for index in range(useful_life_quarters):
            yield Span(self.cohort.shift(quarter * index), depreciation, split_daily)


class DepreciationByCohort(SpanSeriesFamily[Period]):
    label = "Depreciation by cohort"

    def key_label(self, key: Period) -> str:
        return f"{key.end:%Y} Q{((key.end.month - 1) // 3) + 1}"

    def spans(self, period: Period) -> SpanFamilyResult[Period]:
        result: dict[Period, tuple[Span, ...]] = {}
        for cohort in Period.seq(model_start, quarter, period.end):
            cohort_series = self.ctx.get_or_create_family_series(
                self,
                cohort,
                lambda cohort=cohort: type(
                    f"DepreciationCohort{cohort.end:%Y%m%d}",
                    (DepreciationCohort,),
                    {"cohort": cohort},
                ),
            )
            result[cohort] = tuple(cohort_series.query(period).eval())
        return result
```

When summing family values, map over the family value formula:

```py
cohort_values = self.ctx.get(DepreciationByCohort).value(period)
total = cohort_values.map(lambda values: sum(v or 0.0 for v in values.values()))
yield Span(period, total, split_daily)
```

Families can be dynamic with respect to dates and periods, not resolved cell values. If a value condition controls visibility, define possible keys and return `None` or zero where inactive.

## Debugging Dependencies

Prefer a debugger when available. Orcaset also exposes cell dependency graphs:

```py
ctx = Context()
cell = ctx.get(Revenue).query(Period(date(2026, 12, 31), date(2027, 12, 31))).eval()[0]
cell.eval(ctx)
deps = ctx.deps(cell)
print(deps.to_dot())
```

Resolve the cell first when practical. For statement debugging, materialize a narrow period range and inspect `StatementResult.rows`, or query individual lines directly with `.value(...).eval()`.

## Pitfalls

- `Context.get` is invariant by series type; it does not return subclass instances.
