# Quickstart Example

Run from the repo root: `uv run python examples/quickstart/main.py`. Code: [main.py](./main.py).

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

Instead of working with cells directly, users generally work with cell factories representing line items in a model. These `Series` types enable efficient, strongly typed composition of cells.

We can create an initial `Interest` series by subclassing `SpanSeries` and overriding the abstract `spans` method.

```py
class Interest(SpanSeries):
    def spans(self) -> Iterable[Span]:
        s: Span | None = None
        # Yield historical interest accruals
        for s in historical_spans:
            yield s

        # Yield projected interest accruals
        if s is None:
            return
        for period in Period.seq(s.period.end, relativedelta(months=3, day=31)):
            s = Span(
                period=period,
                fn=s.fn * (1 + 0.05 / 4),
                split=split_daily,
            )
            yield s
```

*Interest doesn't depend on the loan balance yet, it just grows at 5%, compounded quarterly. We'll update it later.*

Interest is calculated by first looping over and yielding the historical accruals. It continues by iterating over a sequence of quarterly periods from that last historical period and yielding spans that grow at a 5% quarterly rate. The value definition `fn=s.fn * (1 + 0.05 / 4)` says get the formula from the last span, creates a new `Formula` by multiplying it by `(1 + 5% / 4)`, and assign the new formula to the new span.

> Formulas are overloaded so that they return a new formula when used in arithmetic against numerical values. `fn=s.fn * (1 + 0.05 / 4)` is the same as `fn=s.fn.map(lambda x: None if x is None else x * (1 + 0.05 / 4))` which explicitly creates a new formula by mapping a new values from the old one.

Next, let's define the account balance. A balance is a point-in-time value, so we'll use points instead of spans.

The abstract `PointSeries` class requires the `point` method to be implemented. This method should return a `Formula[float | None]` for a `date` input.

For any date before the start date, we'll just return `None` indicating there's no meaningful balance. For the start date, we'll return a formula for the initial balance value.

```py
start_date = date(2025, 12, 31)
initial_balance = 100.0

class Balance(PointSeries):
    def point(self, dt: date) -> Formula[float | None]:
        if dt < start_date:
            return Formula.pure(None)
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
        interest = self.ctx.get(Interest).query(Period(start_date, dt)).map(sum_spans(0.0))
        return initial_balance + interest
```

Breaking this down:

* `self.ctx.get(Interest)`: Get the interest object from the current context.
* `.query(Period(start_date, dt))`: Query interest for the list of span cells from the start date to the query date. Partial cells are clipped to the query date bounds using the cell's split function. If the query bounds extend outside `Interest`'s range (e.g. if we queried for a period before the series started), pads with spans that have a value of `None`.
* `.map(sum_spans(0.0))`: Map the list of spans to a float by summing their values. Fills `None` value spans with `0.0`.

We can also update `Interest` to depend on the outstanding balance using a similar approach.

```py
interest_rate = 0.05

class Interest(SpanSeries):
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

Cell values are resolved by calling `eval` and passing the model context.

```py
ctx = Context()

cell = historical_spans[0]
print(cell.eval(ctx))
# 1.0
```

To resolve values from a series, first ask the context for an instance of the series using `ctx.get(...)` then query and evaluate the applicable cells.

```py
interest = ctx.get(Interest)
balance = ctx.get(Balance)

print("End Date\tBalance\tInterest")
for period in Period.seq(start_date, period_length, end=date(2026, 12, 31)):
    int_acc = interest.query(period).map(sum_spans(0.0)).eval()
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

## Simplifying the Model

Orcaset comes with many functions for building, combining and evaluating series.

For example, the `point.accumulate` function is a convenience constructor for building point series that start from an initial value and change based on accumulating over a span series. We could redefine the balance line item in a single line:

```py
Balance2 = point.accumulate(start_date, initial_balance, Interest)
```

There are series combinators for `neg`, `scale`, `sum`, `sub`, `mul`, and `div` which can be invoked directly or through regular operator notation. The binary constructors all combine series on a date-aligned basis. This means you can define arbitrary sequence periods and they will be combined correctly.

```py
# OperatingIncome: 100 annually
OperatingIncome = span.define(
    lambda _: [
        Span(p, Formula.pure(100.0), split_daily)
        for p in Period.seq(start_date, relativedelta(years=1))
    ]
)

# Operating income is defined with yearly periods. Orcaset automatically aligns and 
# interpolates periods when combining with Interest which is defined with quarterly periods
PreTaxIncome = OperatingIncome + Interest
Taxes = PreTaxIncome * -0.25
NetIncome = PreTaxIncome - Taxes
```

In addition to the packaged convenience constructors you can, of course, build your own library of constructors to efficiently build models and connect to data sources.
