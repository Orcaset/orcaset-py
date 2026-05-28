# Orcaset Python API Reference: 0.2.0

Use this reference only when the detected Orcaset version is `0.2.x`, or when local source inspection confirms these signatures still match.

Look up definitions in the installed library for any required types not defined here.

## Contents

- Imports
- Periods
- Formulas and Cells
- SpanSeries
- PointSeries
- Context and Resolution
- Statement Views
- Common Patterns
- Dynamic Series Families
- Debugging Dependencies
- Common Pitfalls

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

Examples:

```py
period = Period(date(2025, 12, 31), date(2026, 3, 31))
next_qtr = period.from_end(relativedelta(months=3, day=31))  # (2026-03-31, 2026-06-30)
prior_qtr = period.from_start(relativedelta(months=-3, day=31))  # (2025-09-30, 2025-12-31)
yoy_qtr = period.shift(relativedelta(years=-1))  # (2025-12-31, 2025-03-31)
```

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
class SpanSeries(Series):
    """A period-indexed flow or level series made of spans."""

    def query(self, period: Period) -> Formula[list[Span]]
        """Return spans covering `period`, clipping and filling gaps as needed."""

    def value(self, period: Period) -> Formula[float | None]
        """Return a formula resolving this series value over `period`."""

    @staticmethod
    @abstractmethod
    def agg(spans: list[Span]) -> float | None
        """Reduce queried spans into a single value."""

    @abstractmethod
    def spans(self) -> Iterable[Span]
        """Yield the source spans for this series."""

class SpanSeriesFamily[K: Hashable](Series):
    """A period-indexed collection of generated span series keyed by `K`."""

    def query(self, period: Period) -> Formula[SpanFamilyResult[K]]
        """Return spans for every family key over `period`."""

    def value(self, period: Period) -> Formula[Mapping[K, float | None]]
        """Return reduced values for every family key over `period`."""

    def key_label(self, key: K) -> str
        """Return the display label for a generated family key."""

    @abstractmethod
    def spans(self, period: Period) -> SpanFamilyResult[K]
        """Build spans for every family key over `period`."""

def avg_spans(yf: Callable[[date, date], float], fill: float) -> SpanAggregator
def last_span(fill: float | None) -> SpanAggregator
def no_split(span: Span, dt: date) -> tuple[SpanFormulaTransform, SpanFormulaTransform]
def split_const(_: Span, __: date) -> tuple[SpanFormulaTransform, SpanFormulaTransform]
def split_daily(span: Span, dt: date) -> tuple[SpanFormulaTransform, SpanFormulaTransform]
def sum_spans(fill: float) -> SpanAggregator
def extend(
    base: type[SpanSeries],
) -> Callable[[Callable[[SpanSeries, date | None], Iterable[Span]]], type[SpanSeries]]
    """Create a decorator that extends `base` with continuation spans."""
def from_list(
    values: Iterable[tuple[tuple[date, date], float | None]],
    *,
    agg: SpanAgg,
    split: SpanSplit = no_split,
    name: str = "ListSpanSeries",
) -> type[SpanSeries]
    """Create a span series from explicit date-range value records."""
def periodic(
    start: date,
    freq: relativedelta,
    value: float | None,
    *,
    agg: SpanAgg,
    split: SpanSplit,
    end: date | None = None,
    name: str | None = None,
) -> type[SpanSeries]
    """Create a span series with repeated constant spans."""
def sum(
    series: Sequence[type[SpanSeries]],
    *,
    agg: SpanAgg,
    name: str = "SumSpanSeries",
) -> type[SpanSeries]
    """Create a span series by summing aligned spans across series."""
def sub(
    left: type[SpanSeries],
    right: type[SpanSeries],
    *,
    agg: SpanAgg,
    name: str | None = None,
) -> type[SpanSeries]
    """Create a span series that subtracts `right` from `left`."""
def scale(
    series: type[SpanSeries],
    factor: float,
    *,
    name: str | None = None,
) -> type[SpanSeries]
    """Create a span series scaled by `factor`."""
def neg(series: type[SpanSeries], *, name: str | None = None) -> type[SpanSeries]
    """Create a span series that negates another span series."""
def mul(
    series: Sequence[type[SpanSeries]],
    *,
    agg: SpanAgg,
    name: str = "MulSpanSeries",
) -> type[SpanSeries]
    """Create a span series by multiplying aligned spans across series."""
def div(
    left: type[SpanSeries],
    right: type[SpanSeries],
    *,
    agg: SpanAgg,
    name: str | None = None,
) -> type[SpanSeries]
    """Create a span series that divides `left` by `right`."""
```

- All binary series combinators merge series aligning spans (not by span index).
- Series can be combined with scalars either with regular arithmetic operators or `*_scalar` functions.

Examples:

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

Common constructors and operators:

```py
class PointSeries(Series):
    """Base class for a `Point` factory."""

    def query(self, dt: date) -> Formula[Point]
        """Return the point cell for `dt`, creating and caching it if needed."""

    def value(self, dt: date) -> Formula[float | None]
        """Return a formula resolving this series value at `dt`."""

    @abstractmethod
    def point(self, dt: date) -> Formula[float | None]
        """Subclasses must implement this method to return the point formula for `dt`."""

class PointSeriesFamily[K: Hashable](Series):
    """A date-indexed collection of generated point series keyed by `K`."""

    def query(self, dt: date) -> Formula[PointFamilyResult[K]]
        """Return point cells for every family key at `dt`."""

    def key_label(self, key: K) -> str
        """Return the display label for a generated family key."""

    @abstractmethod
    def points(self, dt: date) -> PointFamilyResult[K]
        """Subclasses must implement this method to return the point cells for every family key at `dt`."""

def accumulate(
    start: date,
    value: float | None,
    changes: type[SpanSeries],
    name: str = "AccumulatedPointSeries",
) -> type[PointSeries]
    """Create a point series by accumulating span changes from a start value."""
def define(
    fn: Callable[[PointSeries, date], Formula[float | None]],
    /,
) -> type[PointSeries]
    """Create a `PointSeries` class from a point formula function."""
def sum(
    series: Sequence[type[PointSeries]],
    *,
    name: str = "SumPointSeries",
) -> type[PointSeries]
    """Create a point series by summing multiple point series."""
def sub(
    left: type[PointSeries],
    right: type[PointSeries],
    *,
    name: str | None = None,
) -> type[PointSeries]
    """Create a point series that subtracts `right` from `left`."""
def scale(
    series: type[PointSeries],
    factor: float,
    *,
    name: str | None = None,
) -> type[PointSeries]
    """Create a point series scaled by `factor`."""
def mul(
    series: Sequence[type[PointSeries]],
    *,
    name: str = "MulPointSeries",
) -> type[PointSeries]
    """Create a point series by multiplying multiple point series."""
def div(
    left: type[PointSeries],
    right: type[PointSeries],
    *,
    name: str | None = None,
) -> type[PointSeries]
    """Create a point series that divides `left` by `right`."""
```

Series can be combined with scalars either with regular arithmetic operators or `*_scalar` functions.

Use `point.accumulate` for roll-forwards driven by a span series. Examples:

```py
Cash = point.accumulate(model_start, initial_cash, TotalCashFlow, name="Cash")
PpeNet = point.accumulate(model_start, initial_ppe_net, PpeNetChange, name="PPE net")
TotalAssets = point.sum([Cash, PpeNet], name="Total assets")
BalanceSheetCheck = point.sub(TotalAssets, TotalEquityAndLiabilities, name="Balance sheet check")
```

## Context and Resolution

`Context` owns series instances, caches cells, resolves formulas, and tracks dependencies.

```py
ctx = Context()
revenue = ctx.get(Revenue)

spans = revenue.query(Period(date(2026, 1, 1), date(2026, 4, 1))).eval()  # Evaluates to `list[Span]`
value = revenue.value(Period(date(2026, 1, 1), date(2026, 4, 1))).eval()  # Evaluates to `float | None`
cash = ctx.get(Cash).value(date(2026, 4, 1)).eval()  # Evaluates to `float | None`

span_cell = spans[0]
ctx.deps(span_cell)  # Get the cell dependency graph for `span_cell`
```

Use `.query(...)` when raw cells or clipped spans/points are needed. Use `.value(...)` when the resolved numeric value is needed. Use one `Context` per model run or scenario.

Do not instantiate series classes directly. Use `ctx.get(SeriesType)`.

## Statement Views

`Stmt`, `Group`, and `Total` define output views. They do not define the model.

Example of creating a statement.

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
```

For date-based point output, use `stmt.values_for_dates(ctx, dates)`. For period output, use `stmt.values(ctx, periods)` or `stmt.values_for_periods(ctx, periods)`.

Format structured `Stmt` output to readable format:

```py
# Prints the statement to a table in the console with fixed width columns
print(fixed_width_table(result, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))
```

Formatters include `fixed_width_table`, `markdown`, and `csv`. Row names will use the `Series.label` value or the class name if no label exits.

## Common Patterns

### Historical spans plus forecaset using `SpanSeries.extend`:

Use `span.extend` when a span line has actuals followed by projections.

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

### Dynamic Series Families

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

## Common Pitfalls

- Do not pass a positive offset to `Period.from_start` unless you want a period starting at `periods.start`.
- `Context.get` is invariant by series type; it does not return subclass instances. Query contexts for the exact type.
- Do not ignore `CellConvergenceError` errors.
