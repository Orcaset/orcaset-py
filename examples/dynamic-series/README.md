# Dynamic Series

*Run the example: `uv run python examples/dynamic-series/main.py`*

Unlike spreadsheets where formulas must be entirely defined upfront, Orcaset can build series dynamically in response to queries. This is a form of meta-programming.

Dynamic series are helpful in building cohort-based analysis (e.g. depreciation schedules, revenue retention, etc.). Cohort schedules in a spreadsheet transpose columns into rows: each cohort group (column) needs a corresponding shedule (row) that spreads the upfront cost or total over future periods.

```txt
Period                    1       2       3     ...
------                  ---     ---     ---     ...
Capital expenditures    100     100     100     ...

Depreciation by cohort
    Period 1            25       25      25     ...
    Period 2                     25      25     ...
    Period 3                             25     ...
    ...

Total depreciation       25      50      75     ...
```

Querying total depreciation over periods `1 - n` requires building and summing over depreciation cohorts for capital expenditures in periods one through `n`. So, we need some way to dynamically build new cohort-level depreciation series based on the queried inputs.

This example demonstrates how to dynamically create new series by building the depreciation schedule above.

## Capital expenditures

First, define the capital expenditure series.

```py
start_date = date(2025, 12, 31)
qtr_offset = relativedelta(months=3, day=31)

@span.define(agg=sum_spans(0.0), label="Capital Expenditures")
def capex(_) -> Iterable[Span]:
    for period in Period.seq(start_date, qtr_offset):
        yield Span(period, Formula.pure(100.0), split_daily)
```

This series simpley produces quarterly expenditures of `100.0` forever.

## Depreciation cohorts

There are three main components to building the cohort series:

* **Keys:** Generated series need a unique, hashable key that will identify each generated series with a family.
* **Active key function:** Given a query period, return the keys for series active in that period.
* **Series factory function:** Function that receives the cohort key and returns a fresh series for that key.

Orcaset provides `keyed` constructors that manages these concepts to make them easier to work with and cache for efficiency.

Keys can by any hashable object (`str`, `int`, or any hashable type). In this case, the keys will be the cohort periods.

```py
def cohort_keys(period: Period) -> Iterable[Period]:
    return takewhile(lambda c: c.start < period.end, Period.seq(start_date, qtr_offset))
```

This function loops over calendar quarters and returns any period that starts before the query period ends. It technically returns too many cohort keys. Depreciation expense doesn't start until the *following* period and ends after four quarters. We could narrow the function to *only* return keys for series with a non-zero depreciation expense in the period. However, this approach is more robust against changes (like increasing the useful life) and doesn't have a material impact on performance for this example.


Next, we need to define a series factory function that takes a key (a cohort period) and returns a new series for that cohort.

```py
useful_life_qtrs = 4

def create_cohort_series(cohort: Period) -> SpanSeriesDef:

    # Create the new series
    @span.define(agg=sum_spans(0.0), label=f"Qtr {cohort.end}")
    def depreciation_cohort(ctx: Context) -> Iterable[Span]:
        # Get total capex over the cohort period
        cohort_capex = capex.value(ctx, cohort)

        # Depreciate evenly over the next four calendar quarters
        depreciation = cohort_capex / useful_life_qtrs
        qtrs = Period.list(cohort.end, qtr_offset, cohort.end + qtr_offset * useful_life_qtrs)
        for qtr in qtrs:
            yield Span(qtr, depreciation, split_daily)

    return depreciation_cohort
```

For any cohort period, `create_cohort_series` produces a new series that queries `capex` for that cohort and yields spans in even quarterly straightline installments over the next for quarters. A quick test confirms this behavior:

```py
cohort = create_cohort_series(Period(start_date, start_date + qtr_offset))

ctx = Context()
for period in Period.list(start_date, qtr_offset, date(2027, 6, 30)):
    print(f"{period}: {cohort.value(ctx, period).eval()}")

# Period(2025-12-31, 2026-03-31): 0.0
# Period(2026-03-31, 2026-06-30): 25.0
# Period(2026-06-30, 2026-09-30): 25.0
# Period(2026-09-30, 2026-12-31): 25.0
# Period(2026-12-31, 2027-03-31): 25.0
# Period(2027-03-31, 2027-06-30): 0.0
```

Depreciation starts the following quarter and runs off in four equal quarterly installments. This confirms the series factory function is working propertly.

`create_cohort_series` creates a new series every time it's called. If an evaluation run needs to get series over the same period multiple times, we shouldn't get fresh series each time. Instead, new series should be created on the first call, cached, and returned in subsequent calls.

The `keyed` constructor creates an object that does exactly that. Rather than working with the factory function directly, `span.keyed` creates an object that will automatically manage caching. 

```py
depreciation_cohorts = span.keyed(
    keys=cohort_keys,
    series=create_cohort_series,
    label="Depreciation Cohorts",
)
```

`depreciation_cohorts` manages building or retrieving series from the context if they already exist wrapped in simple accessor methods. 

## Accessing dynamic series

Finally, will consume dynamically generated series by summing them into a total depreciation line item.

```py
@span.define(agg=sum_spans(0.0), label="Total Depreciation")
def total_depreciation(ctx: Context) -> Iterable[Span]:

    for period in Period.seq(start_date, qtr_offset):
        # Get the active cohorts for the period
        cohorts = depreciation_cohorts.items(ctx, period)
        # Query cohort values for the period
        cohort_values = [cohort.value(ctx, period) for _, cohort in cohorts]
        # Sum the cohort values
        total: Formula[float | None] = Formula.sequence(cohort_values).map(
            lambda v: sum(v or 0.0 for v in v)
        )
        # Yield the total
        yield Span(period, total, no_split)
```

`total_depreciation` is a noraml series with a single extra step to get derived series dependencies using `depreciation_cohorts.items(ctx, period)`.

## Statement output

Keyed dynamic series can be structured into statement outputs as regualr arguments. 

```py
ctx = Context()
stmt = Stmt(
    capex,
    Total(total_depreciation, [depreciation_cohorts]),
)
```

The built-in formatters will automatically expand them to show detail for all generated series as well.

```py
periods = Period.list(start_date, qtr_offset, date(2027, 12, 31))
results = stmt.values(ctx, periods)
print(fixed_width_table(results, date_formatter=lambda dt: f"{dt:%Y-%m-%d}"))

# Start                             2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30
# End                   2025-12-31  2026-03-31  2026-06-30  2026-09-30  2026-12-31  2027-03-31  2027-06-30  2027-09-30  2027-12-31
# Capital Expenditures                  100.00      100.00      100.00      100.00      100.00      100.00      100.00      100.00

#     Qtr 2026-03-31                      0.00       25.00       25.00       25.00       25.00        0.00        0.00        0.00
#     Qtr 2026-06-30                      0.00        0.00       25.00       25.00       25.00       25.00        0.00        0.00
#     Qtr 2026-09-30                      0.00        0.00        0.00       25.00       25.00       25.00       25.00        0.00
#     Qtr 2026-12-31                      0.00        0.00        0.00        0.00       25.00       25.00       25.00       25.00
#     Qtr 2027-03-31                      0.00        0.00        0.00        0.00        0.00       25.00       25.00       25.00
#     Qtr 2027-06-30                      0.00        0.00        0.00        0.00        0.00        0.00       25.00       25.00
#     Qtr 2027-09-30                      0.00        0.00        0.00        0.00        0.00        0.00        0.00       25.00
#     Qtr 2027-12-31                      0.00        0.00        0.00        0.00        0.00        0.00        0.00        0.00

# --------------------------------------------------------------------------------------------------------------------------------
# Total Depreciation                      0.00       25.00       50.00       75.00      100.00      100.00      100.00      100.00  
```

Examining the output confirms total depreciation expense and depreciation detail is correct. Capital expenditures begin depreciating in the quarter after they occur and are expensed in four even charges.

## Additional considerations

This example only covers dynamice span series. The concepts carry over to analous point series as well. Additionally, while periods are common and intuitive keys for cohort analysis, keys can refer to any unique identifier, for example loan tranche name or financing round.

Lastly, dynamic series can be functions of time but not cell values. In other words, modeling "create series A if the value of series B on date X is Y" is not possible. Instead, create series eagerly and make values conditional on other values (i.e. "create series A and set its values based on series B).
