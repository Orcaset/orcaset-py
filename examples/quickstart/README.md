# Quickstart Example

*Run from the repo root: `uv run python examples/quickstart/main.py`. Code: [main.py](./main.py).*

This example introduces basic concepts by building a simple model of an interest-bearing account. The model has two line items:

* **Interest:** Three historical quarters, then projections accruing at 5%, compounding quarterly
* **Balance:** Starts at 100 and grows based on accrued interest

## Concepts

### Cells

Cells are the fundamental building block in Orcaset models. There are two basic cell variants: `Span` cells which represent a value over a period of time and `Point` cells which represent a value at a specific date. Conceptually, income and cash flow items are built from `Span` cells while balance sheet items are built from `Point` cells.

Cells delay value resolution by holding `Formula` objects instead of raw numerical values directly. This permits structured cell dependencies, including circular references, without hitting recursion errors. The simplest formula is `Formula.pure(...)` which just returns the wrapped value.

Example cell construction:

```py
balance = Point(date(2025, 12, 31), Formula.pure(42))
accrual = Span(Period(date(2025, 12, 31), date(2026, 3, 31)), Formula.pure(100), split_daily)
```

`Span` objects also carry a splitting function (e.g. `split_daily`) so that Orcaset can interpolate partial periods automatically. If a span cannot be meaningfully split, use `no_split` which raises an error if ever invoked.

In our simple model, we can structure a list of historical interest accruals into a list of `Span` objects:

```py
interest_data = [
    ((date(2025, 12, 31), date(2026, 3, 31)), 1.00),
    ((date(2026, 3, 31), date(2026, 6, 30)), 2.00),
    ((date(2026, 6, 30), date(2026, 9, 30)), 3.00),
]

historical_spans = [Span(Period(*c[0]), Formula.pure(c[1]), split_daily) for c in interest_data]
```

### Series

#### `Interest`

Instead of working with cells directly, users generally work with cell factories representing line items in a model. These `Series` types enable efficient, strongly typed composition of cells.

We can create an initial `Interest` series by subclassing `SpanSeries` and overriding the abstract `spans` method.

```py
interest_rate = 0.05

class Interest(SpanSeries):

    def spans(self) -> Iterable[Span]:
        s: Span | None = None
        # Yield historical interest accruals
        for s in historical_spans:
            yield s

        # Yield projected interest accruals
        if s is None:
            return

        # Initial example: grow at 5% compounding quarterly
        for period in Period.seq(s.period.end, relativedelta(months=3, day=31)):
            s = Span(
                period=period,
                fn=s.fn * (1 + interest_rate / 4),
                split=split_daily,
            )
            yield s
```

*Interest doesn't depend on the account balance yet, it just grows at 5%, compounded quarterly. We'll update it later.*

Interest is calculated by first looping over and yielding the historical accruals. It continues by iterating over a sequence of quarterly periods from that last historical period and yielding spans that grow at a 5% annual rate. The value definition `fn=s.fn * (1 + interest_rate / 4)` gets the formula from the last span, creates a new `Formula` by multiplying it by `(1 + 0.05 / 4)`, and assigns the new formula to the new span.

> Formulas are overloaded so that they return a new formula when used in arithmetic against numerical values. `fn=s.fn * (1 + 0.05 / 4)` is the same as `fn=s.fn.map(lambda x: None if x is None else x * (1 + 0.05 / 4))` which explicitly creates a new formula by mapping a new value from the old one.

In addition to defining how spans should be split, we also need to define how spans should be aggregated. The `agg` attribute is a static function that reduces a list of `Span`s to a `float | None` value. `sum_spans(0.0)` is a convenience constructor for building a function that sums over span values, filling any null values with zero.

```py
class Interest(SpanSeries):
    agg = sum_spans(0.0)
    # ...
```

#### `Balance`

Next, let's define the account balance. A balance is a point-in-time value, so we'll use points instead of spans.

The abstract `PointSeries` class requires the `point` method to be implemented. This method should return a `Formula[float | None]` for a `date` input.

For any date before the start date, we'll just return `None` indicating there's no meaningful balance. For the start date, we'll return a formula for the initial balance value.

```py
start_date = date(2025, 12, 31)
initial_balance = 100.0

class Balance(PointSeries):
    def point(self, dt: date) -> Formula[float | None]:
        # Return None for dates before the start date
        if dt < start_date:
            return Formula.pure(None)

        # Return the initial balance for the start date
        if dt == start_date:
            return Formula.pure(initial_balance)
        # ...
```

For any date after the start date, we can define the value as `(initial balance) + (total accrued interest from the start date to the query date)`. In order to resolve dependencies between series, we need to introduce `Context`.

### Context

A `Context` object holds all state for a model. A context object instantiates series instances, manages resolution between series, and caches cell values to improve performance. Series and cells should be built as pure functions with all state held by the context.

Series are instantiated with the current `ctx` object which we can use to get the interest and the balance series.

```py
class Balance(PointSeries):
    def point(self, dt: date) -> Formula[float | None]:
        # ...
        
        interest = self.ctx.get(Interest).value(Period(start_date, dt))
        return initial_balance + interest
```

Breaking this down:

* `self.ctx.get(Interest)`: Get the interest object from the current context
* `.value(Period(start_date, dt))`: Query interest from the starting date to the query date

We can also update `Interest` to depend on the outstanding balance using a similar approach.

```py
class Interest(SpanSeries):
    agg = sum_spans(0.0)

    def spans(self) -> Iterable[Span]:
        # ...

        for period in Period.seq(s.period.end, relativedelta(months=3, day=31)):
            yield Span(
                period=period,
                fn=self.ctx.get(Balance).value(period.start) * interest_rate / 4,
                split=split_daily,
            )
```

### Resolving values

Cell values are resolved by calling `eval` and passing the model context. For example, we can evaluate the first historical interest span with this code.

```py
ctx = Context()

cell = historical_spans[0]
print("\nInitial interest cell value: ", cell.eval(ctx))
# Initial interest cell value:  1.0
```

To resolve values from a series, first ask the context for an instance of the series using `ctx.get(...)` then query and evaluate the applicable cells using `.value(...).eval()`.

```py
interest = ctx.get(Interest)
balance = ctx.get(Balance)

print("End Date\tBalance\tInterest")
for period in Period.seq(start_date, period_length, end=date(2026, 12, 31)):
    int_acc = interest.value(period).eval()
    bal = balance.value(period.end).eval()
    print(f"{period.end:%m/%d/%Y}\t{bal:,.2f}\t{int_acc:,.2f}")

# End Date        Balance Interest
# 01/31/2026      100.34  0.34
# 02/28/2026      100.66  0.31
# 03/31/2026      101.00  0.34
# ...
```

`Context.get(SomeSeriesClass)` checks whether any instance of `SomeSeriesClass` already exists in the model. If so, it returns the existing instance. If not, it creates and returns a new instance. 

> `Context.get` is invariant on the class argument. `ctx.get(SomeClass)` always returns an instance of `SomeClass`. It will not return any instances of a subclass of `SomeClass`, even if they already exist in the model.

Notice that we defined interest periods on a quarterly basis but queried on a monthly basis. Orcaset automatically interpolates partial periods in response to the monthly queries. In this case, interest spans were created using the `split_daily` function which pro rates partial periods based on the relative proportion of days.

## Simplifying the Model

Orcaset comes with many functions for building and combining series.

For example, the `point.accumulate` function is a convenience constructor for building point series that start from an initial value and change based on accumulating over a span series. We could redefine the balance line item in a single line:

```py
Balance2 = point.accumulate(start=start_date, value=initial_balance, changes=Interest)
```

There are series combinators for `neg`, `scale`, `sum`, `sub`, `mul`, and `div`. Scalar operations can use regular operator notation, while binary and multi-series span combinations use explicit constructors with an `agg` function. The binary constructors all combine series on a date-aligned basis. This means you can define arbitrary sequences of periods and they will be combined correctly.

```py
# OperatingIncome: 100 annually
OperatingIncome = span.define(
    lambda _: [
        Span(p, Formula.pure(100.0), split_daily)
        for p in Period.seq(start_date, relativedelta(years=1))
    ],
    agg=sum_spans(0.0),
)

# Operating income is defined with yearly periods. Orcaset automatically aligns and
# interpolates periods when combining with Interest which is defined with quarterly periods
PreTaxIncome = span.sum([OperatingIncome, Interest], agg=sum_spans(0.0))
Taxes = PreTaxIncome * -0.25
NetIncome = span.sum([PreTaxIncome, Taxes], agg=sum_spans(0.0))
```

Beyond the packaged convenience constructors you can, of course, build your own library of constructors to efficiently build models and connect to data sources.

### Structured output

In addition to manually querying values, we can create statements views using the `stmt` module. Statements create views that can be queried with a single call and formatted into structure output (CSV, markdown, JSON, etc).

For example, to create this statement structure:

```txt
Income statement(Group)
└── Net income (Total)
    ├── Pre-tax income (Total)
    │   ├── Operating income (Series)
    │   └── Interest (Series)
    └── Taxes (Series)
Balance sheet (Group)
└── Balance (Series)
```

we would define this statement:

```py
# Add human-readable labels
NetIncome.label = "Net Income"
Taxes.label = "Taxes"
PreTaxIncome.label = "Pre-Tax Income"
OperatingIncome.label = "Operating Income"


# Create statement
stmt = Stmt(
    Group([Total(NetIncome, [Total(PreTaxIncome, [OperatingIncome, Interest]), Taxes])]),
    Group([Balance]),
)
```

We can materialize all the cells in the statement, which returns structured output that we can format to a table and print to the console.

```py
periods = Period.list(start_date, relativedelta(years=1), date(2030, 12, 31))
results = stmt.values(ctx, periods)
formatted_table = fixed_width_table(results)
print(formatted_table)

# Start                               2025-12-31  2026-12-31  2027-12-31  2028-12-31  2029-12-31
# End                     2025-12-31  2026-12-31  2027-12-31  2028-12-31  2029-12-31  2030-12-31

#       Operating Income                  100.00      100.00      100.00      100.00      100.00
#       Interest                            7.33        5.47        5.75        6.04        6.35
# ----------------------------------------------------------------------------------------------
#     Pre-Tax Income                      107.33      105.47      105.75      106.04      106.35
#     Taxes                               -26.83      -26.37      -26.44      -26.51      -26.59
# ----------------------------------------------------------------------------------------------
#   Net Income                             80.49       79.10       79.31       79.53       79.76


#   Balance                   100.00      107.33      112.79      118.54      124.58      130.92
```

The `formatters` module currently includes `fixed_width_table`. User-defined converters to other formats are easy to create from the structured statement results.

## Summary

This example introduces the core Orcaset concepts. Review the other examples for guides on common scenarios, or get started by asking any coding agent to build a new model!
