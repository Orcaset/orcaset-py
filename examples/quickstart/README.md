# Quickstart Example

*Run from the repo root: `uv run python examples/quickstart/main.py`. Code: [main.py](./main.py).*

This example introduces Orcaset by building a simple recursive model of an interest-bearing account. The model has two line items:

* **Interest:** Three historical quarters, then projected quarterly interest
* **Balance:** Starts at 100 and grows based on accrued interest

## Concepts

### Cells

Cells are the fundamental building block in Orcaset models. There are two basic cell variants: `Span` cells, which represent a value over a period of time, and `Point` cells, which represent a value at a specific date. Conceptually, income and cash flow items are usually built from `Span` cells while balance sheet items are usually built from `Point` cells.

Cells hold `Formula` objects instead of raw numerical values directly. This lets Orcaset represent structured dependencies, including circular references, without immediately recursing through the model. The simplest formula is `Formula.pure(...)`, which just returns the wrapped value.

Example cell construction:

```py
balance = Point(date(2025, 12, 31), Formula.pure(42))
accrual = Span(Period(date(2025, 12, 31), date(2026, 3, 31)), Formula.pure(100), split_daily)
```

`Span` objects also carry a splitting function such as `split_daily` so Orcaset can interpolate partial periods automatically. If a span cannot be meaningfully split, use `no_split`, which raises an error if Orcaset ever needs to split that span.

In this model, we can structure historical interest accruals into a list of `Span` objects:

```py
interest_data = [
    ((date(2025, 12, 31), date(2026, 3, 31)), 1.00),
    ((date(2026, 3, 31), date(2026, 6, 30)), 2.00),
    ((date(2026, 6, 30), date(2026, 9, 30)), 3.00),
]

historical_spans = [Span(Period(*c[0]), Formula.pure(c[1]), split_daily) for c in interest_data]
```

### Series

Instead of working with cells directly, users generally work with series definitions that represent line items in a model. A `SpanSeriesDef` defines a source timeline of spans and an aggregation function. A `PointSeriesDef` defines a source timeline of points and optional interpolation behavior for non-source dates.

Series definitions are immutable definition objects. They are not instantiated from a `Context`; instead, pass an explicit `Context` to `.query(...)` or `.value(...)` when resolving values.

#### `interest`

We can create an initial `interest` series with the `@span.define(...)` decorator. This first version yields the historical accruals, then projects interest by growing the prior quarter's formula at a 5% annual rate compounded quarterly.

```py
interest_rate = 0.05


@span.define(agg=sum_spans(0.0), label="Interest")
def interest(ctx: Context) -> Iterable[Span]:
    s: Span | None = None
    for s in historical_spans:
        yield s

    if s is None:
        return

    for period in Period.seq(s.period.end, relativedelta(months=3, day=31)):
        s = Span(
            period=period,
            fn=s.fn * (1 + interest_rate / 4),
            split=split_daily,
        )
        yield s
```

The `agg=sum_spans(0.0)` argument defines how a list of spans should be reduced to one value when you call `interest.value(...)`. `sum_spans(0.0)` sums span values and fills `None` values with zero.

The value definition `fn=s.fn * (1 + interest_rate / 4)` gets the formula from the last span and creates a new `Formula` by multiplying it by `(1 + 0.05 / 4)`.

> Formulas are overloaded so arithmetic operations returns new formulas. `s.fn * (1 + 0.05 / 4)` is equivalent to `s.fn.map(lambda x: None if x is None else x * (1 + 0.05 / 4))`.

#### `balance`

Next, let's define the account balance. A balance is a point-in-time value, so we'll use points instead of spans.

The `@point.define(...)` decorator creates a point series from a source point timeline. For this model, the only source point is the starting balance. The interpolation function calculates values for every other date.

```py
start_date = date(2025, 12, 31)
initial_balance = 100.0


def balance_value(ctx: Context, dt: date) -> Formula[float | None]:
    if dt < start_date:
        return Formula.pure(None)

    if dt == start_date:
        return Formula.pure(initial_balance)

    interest_value = interest.value(ctx, Period(start_date, dt))
    return initial_balance + interest_value


@point.define(interpolate=balance_value, label="Balance")
def balance(_: Context) -> Iterable[Point]:
    yield Point(start_date, Formula.pure(initial_balance))
```

Breaking down the interpolation:

* Dates before the start date return `None`
* The start date returns the initial balance
* Later dates return the initial balance plus total interest from the start date to the query date

### Context

A `Context` object owns model state. It materializes source timelines, caches cells and series, tracks dependencies, and solves recursive cell formulas.

The current API passes `Context` explicitly:

```py
interest_value = interest.value(ctx, Period(start_date, dt))
balance_value = balance.value(ctx, dt)
```

We can now update `interest` to depend on the outstanding beginning balance instead of simply compounding from the last interest value:

```py
@span.define(agg=sum_spans(0.0), label="Interest")
def interest(ctx: Context) -> Iterable[Span]:
    s: Span | None = None
    for s in historical_spans:
        yield s

    if s is None:
        return

    for period in Period.seq(s.period.end, relativedelta(months=3, day=31)):
        yield Span(
            period=period,
            fn=balance.value(ctx, period.start) * interest_rate / 4,
            split=split_daily,
        )
```

At this point the model is recursive: projected `interest` depends on `balance`, and `balance` depends on cumulative `interest`. Orcaset represents both sides as formulas and resolves the cells through the context.

### Resolving Values

Cell values are resolved by calling `eval` and passing the model context. For example, we can evaluate the first historical interest span with this code:

```py
ctx = Context()

cell = historical_spans[0]
print("\nInitial interest cell value: ", cell.eval(ctx))
# Initial interest cell value:  1.0
```

To resolve values from a series, pass the same context into `.value(...)` and then evaluate the returned formula.

```py
monthly_period = relativedelta(months=1, day=31)

print("End Date\tBalance\tInterest")
for period in Period.seq(start_date, monthly_period, end=date(2026, 12, 31)):
    int_acc = interest.value(ctx, period).eval()
    bal = balance.value(ctx, period.end).eval()
    print(f"{period.end:%m/%d/%Y}\t{bal:,.2f}\t{int_acc:,.2f}")

# End Date        Balance Interest
# 01/31/2026      100.34  0.34
# 02/28/2026      100.66  0.31
# 03/31/2026      101.00  0.34
# ...
```

`interest.query(ctx, period)` returns a `Formula[list[Span]]` for the span cells covering the requested period. `interest.value(ctx, period)` maps those spans through the series aggregation function. `balance.query(ctx, dt)` returns a `Point` cell, while `balance.value(ctx, dt)` returns a formula that evaluates that point through the context.

Notice that interest periods are defined quarterly but queried monthly. Orcaset automatically clips and interpolates partial periods for the monthly queries. In this case, interest spans use `split_daily`, which prorates partial periods based on the relative number of days.

## Simplifying the Model

Orcaset comes with helpers for building and combining series definitions.

The historical interest series can be created directly from records:

```py
historical_interest = span.from_list(
    interest_data,
    agg=sum_spans(0.0),
    split=split_daily,
    label="Interest 2",
)
```

Then `span.extend(...)` can append projected spans after the last historical span:

```py
@span.extend(historical_interest)
def interest_2(ctx: Context, start: date) -> Iterable[Span]:
    for period in Period.seq(start, relativedelta(months=3, day=31)):
        yield Span(period, balance_2.value(ctx, period.start) * interest_rate / 4, split_daily)
```

The continuation can refer to `balance_2` even though `balance_2` is assigned below because Python resolves that name when the function body runs, not when the decorator creates `interest_2`.

The `point.accumulate(...)` helper creates a point series that starts from an initial value and accumulates span-series changes. This lets us redefine the balance line item in one expression:

```py
balance_2 = point.accumulate(start_date, initial_balance, interest_2, label="Balance 2")
```

There are also series combinators for `neg`, `scale`, `sum`, `sub`, `mul`, and `div`. Formula values support regular arithmetic operators; series combinations use explicit constructors or methods so Orcaset can align source timelines correctly.

```py
@span.define(agg=sum_spans(0.0), label="Operating Income")
def operating_income(ctx: Context) -> Iterable[Span]:
    return [
        Span(p, Formula.pure(100.0), split_daily)
        for p in Period.seq(start_date, relativedelta(years=1))
    ]


pre_tax_income = span.sum(
    [operating_income, interest],
    agg=sum_spans(0.0),
    label="Pre-Tax Income",
)
taxes = span.scale(pre_tax_income, -0.25, label="Taxes")
net_income = span.sum([pre_tax_income, taxes], agg=sum_spans(0.0), label="Net Income")
```

Operating income is defined with yearly periods while interest is defined with quarterly periods. Orcaset aligns and interpolates periods when combining them.

Beyond the packaged helpers, you can build your own constructors to assemble models and connect to data sources.

### Structured Output

In addition to manually querying values, we can create statement views using the `stmt` module. Statements create structures that can be queried with a single call and formatted into fixed-width, markdown, or CSV tables.

For example, this statement:

```py
stmt = Stmt(
    Group([Total(net_income, [Total(pre_tax_income, [operating_income, interest]), taxes])]),
    Group([balance]),
)
```

represents this structure:

```txt
Group
└── Net Income (Total)
    ├── Pre-Tax Income (Total)
    │   ├── Operating Income (Series)
    │   └── Interest (Series)
    └── Taxes (Series)
Group
└── Balance (Series)
```

We can materialize all cells in the statement, format the result as a fixed-width table, and print it to the console:

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

The `formatters` module includes `fixed_width_table`, `markdown_table`, and `csv_table`. User-defined converters can be built from the structured `StatementResult`.

## Summary

This example introduces the core Orcaset concepts: cells, formulas, span series, point series, contexts, helper constructors, and statement output. Review the other examples for guides on common scenarios, or get started by asking a coding agent to build a new model.
