# Orcaset patterns

## Timeline construction

Anchor named financial periods on month-end dates unless directed otherwise:

```python
MODEL_START = date(2026, 12, 31)
MONTH = relativedelta(months=1, day=31)
periods = Period.seq(MODEL_START, MONTH)
```

Yield keys in strictly ascending chronological order. Avoid duplicate keys
unless the relevant API explicitly defines their behavior. Keep rollforward
periods contiguous so each beginning balance links to the preceding ending
balance. Because overlapping `Period` objects are only partially ordered, do
not use `sorted()`, `min()`, or `max()` on potentially overlapping periods.

## Growing flow series

Seed the first period with a constant, then each later cell reads the prior period:

```python
@PeriodSeries.define("Revenue", accrue)
def revenue() -> Iterator[tuple[Period, float | CellFactory[float]]]:
    periods = Period.seq(MODEL_START, MONTH)
    yield next(periods), INITIAL_REVENUE
    for k in periods:
        def factory(p: Period = k) -> Step[float]:
            prior = yield from get_at(revenue, p.shift(-MONTH))
            if isna(prior):
                return 0.0
            return prior * (1 + GROWTH * YF.act360(p.start, p.end))
        yield k, factory
```

Prefer `p.shift(-MONTH)` or `p.from_start(-MONTH)` consistently with how periods were built.

Name and apply rates with explicit units. Distinguish periodic rates such as
`MONTHLY_GROWTH` from annual rates such as `ANNUAL_GROWTH`. Do not apply an
annual rate once per month without conversion or day-count scaling. For annual
compound growth over a modeled period, use:

```python
return prior * (1 + ANNUAL_GROWTH) ** YF.cmonthly(p.start, p.end)
```

Use a linear accrual convention only when the model explicitly requires it.

## Margin-driven lines

```python
cost_of_revenue = (revenue * COST_OF_REVENUE_MARGIN).named("Cost of revenue")
gross_profit = (revenue + cost_of_revenue).named("Gross profit")
```

Keep sign conventions explicit in the assumption (e.g. expenses as negative margins).

## Flat constant series

```python
operating_expenses = PeriodSeries(
    "Operating expenses",
    lambda: zip(Period.seq(MODEL_START, MONTH), repeat(OPERATING_EXPENSES_AMOUNT)),
    accrue,
)
```

## Balance-sheet rollforward (date-keyed)

Stocks are `DateSeries` with `exact`. Initial balance at `MODEL_START`; each later date equals prior balance ± period flows. Discover periods from a related flow series via `get(flow.keys())`:

```python
def cash_cells() -> CellStream[date, float]:
    periods = yield from get(total_cash_flow.keys())
    yield MODEL_START, INITIAL_CASH
    for k in periods:
        def factory(p: Period = k) -> Step[float]:
            bal = yield from get_at(cash, p.start)
            flow = yield from get_at(total_cash_flow, p)
            if isna(bal) or isna(flow):
                raise ValueError(f"missing inputs for cash at {p.end}")
            return bal + flow
        yield k.end, factory

cash = DateSeries("Cash", cash_cells, exact)
```

PPE / retained earnings follow the same shape (multiple flows in the factory).

## Cross-statement links

- Depreciation on the income statement can read beginning PPE: `get_at(ppe_net, p.start)`.
- Cash flow add-backs: `depreciation_add_back = (-depreciation).named("...")`.
- Capex as a margin of revenue: `(revenue * CAPEX_MARGIN).named("Capital expenditures")`.

## Nested statement layout

Mirror presentation hierarchy with nested `Total` / `Group`:

```python
income_stmt = Group(
    [
        Total(
            net_income,
            [
                Total(
                    ebit,
                    [
                        Total(gross_profit, [revenue, cost_of_revenue]),
                        operating_expenses,
                        depreciation,
                    ],
                ),
                income_tax,
            ],
        )
    ]
)

stmt = Stmt(income_stmt, cash_flow_stmt, balance_sheet_stmt)
results = stmt.values(ctx, periods)
```

## Cohort schedules

When each spend period opens a multi-period schedule, use `MapItemsSeries` (see `examples/capex.py`): map each source key to a child `Series`, then map again to sum cohorts at a query period.

## Historical and forecast periods

Keep sourced historical values, forecast assumptions, and calculated outputs
conceptually separate. Define the forecast cutoff explicitly. Seed recursive
forecast lines from the final historical balance or flow. Test the first
forecast period independently because most timing and missing-data errors occur
at that boundary.

## Non-additive metrics

Do not sum monthly ratios to produce a quarterly or annual ratio. Resolve the
reporting-period numerator and denominator first, then divide. Apply the same
principle to margins, prices, per-share measures, and averages, choosing and
documenting an economically appropriate weighting method.

## Model validation

Assert invariants rather than relying only on formatted output:

- Require the balance-sheet check to be zero within an explicit tolerance.
- Reconcile ending cash to beginning cash plus net cash flow.
- Reconcile retained earnings to beginning retained earnings, net income, and distributions.
- Verify each subtotal against its displayed children.
- Fail when a required input resolves to `Na`.
- Verify the exact boundaries of every requested reporting period.

```python
from math import isclose

for period in periods:
    check = ctx.get_at(balance_sheet_check, period.end)
    if isna(check) or not isclose(check, 0.0, abs_tol=0.01):
        raise AssertionError(f"balance sheet does not balance at {period.end}: {check}")
```

Inspect dependencies for at least one ordinary forecast period and the first
period at each historical/forecast or frequency boundary. Run the repository's
formatter, configured type checker, and tests. A model is complete only when
the type checker emits no errors or warnings. Do not use static type casts,
`type: ignore`, checker-specific suppression comments, or equivalent mechanisms
to obtain a clean result.

## Debugging dependencies

```python
print(ctx.dependencies(costs, some_period))
```

Use after a surprising value; the tree shows which `get_at` edges were resolved in that run.
