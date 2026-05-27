# Orcaset Modeling Patterns

Use this reference for modeling workflow and financial-model structure that should remain mostly stable across Orcaset versions. Check the versioned API reference for exact signatures.

## Code Structure

Simple projects (about 20 line items or fewer) can be put in a single file. Larger projects should split code into logical groupings so that it is easier to navigate and maintain. Code should be organized into input, engine, and output groups regardless of whether it's in a single file or many files.

- Inputs: This includes assumptions, historicals, configurations, and any other input data (e.g. input file parsers). Inputs should be logically grouped across on or more files/modules (e.g. `assumptions.py`, `parse.py`, etc). Follow best practices by keeping a clean data-calculation engine boundary.
- Calculation engine: The core financial model code. This includes series definitions and any helper functions used by models. For large models, group into logical modules (e.g. `income.py`, `balance_sheet.py`, `footnotes.py`, `checks.py`, etc.).
- Outputs: The presentation layer. Defining statement views (`stmt` module), printing, and writing output are part of the output layer. All output variables (e.g. query dates and periods) are considered part of the output. Tracing calculations or dependencies (`Context.deps`) by be part of the ouput or a separate debug layer depending on context.

MAINTAIN CLEAR BOUNDARIES BETWEEN CONCERNS, ESPECIALLY AS MODEL COMPLEXITY GROWS.

## Series

Use span series for values over periods. The splitting and aggregation methods should be consistent with intended representation, e.g. flow or level.

- Flows: Represents a flow over time such as a revenue accrual, cash flow, or change in value over time. Usually modeled with a sum aggregator over spans.
- Levels: Represents a value for a given duration, such as the number of available units, active widgets, or interest rate for a specific period of time. Usually modeled with a constant split function and an aggregator that preserves level (e.g. last span or average).

Use point series for values at dates:

- Generally represents balances as of a specific date (e.g. balance sheet items).

When a financial concept could be either a rate or a balance over time, choose deliberately. Rates represented as spans usually need average or last-value aggregation, not sum aggregation.

DO NOT add series termination dates to series. Prefer infinite series unless there's a semantic reason a series should terminate (e.g. loan balane ends becuase it matures, revenue from client stops because the contract ends).

## Forecast Relationships

Prefer formulas that read model relationships at query time. Querying series enables calculation tracing.

Good:

```py
for period in Period.seq(first_projection_date, month):
    prior_period = period.from_start(relativedelta(months=-1, day=31))
    prior = self.ctx.get(Revenue).value(prior_period)
    yield Span(period, prior * (1 + monthly_growth), split_daily)
```

Not good:

```py
value = initial_value
for period in Period.seq(first_projection_date, month):
    yield Span(period, value, split_daily)
    value *= (1 + monthly_growth)
```

For missing values:

- Return `Formula.pure(None)` when a line does not exist before/after a date or the value is undefined.
- Use zero only when zero is the financial assumption.
- Use `Formula.map` and `Formula.map2` for custom missing-value rules.

## Historical Actuals and Projections

Build projection lines as continuations (e.g. using `spans.extend`) instead of mixing actuals and forecasts in a single opaque loop.

Example:

```py
HistProductSales = span.from_list(
    historicals,
    agg=sum_spans(0.0),
    split=split_daily,
    name="Product sales (historical)"
)

@span.extend(HistProductSales)
def ProductSales(self: SpanSeries, start: date | None) -> Iterable[Span]:
    if start is None:
        return
    for period in Period.seq(start, qtr_offset):
        prior_value = self.ctx.get(ProductSales).value(prior_year_period(period))
        yield Span(period, prior * (1 + product_sales_yoy_growth), split_daily)
```

## Dynamic Schedules

Use series families for schedules where rows are discovered from the query period:

- depreciation cohorts
- customer cohorts
- loan tranches
- debt maturities
- product or segment detail
- vintage analyses

Keep possible keys date-driven or configuration-driven. Generated series can depend on periods or dates, but they cannot depend on cell values. The cell value resolver must but able to build the full cell graph prior to value resolution.

## Output

- Use the `stmt` module to build structured output views.
- Use the `formatters` module to structure `stmt` outputs as fixed-width tables, CSV, or markdown output. Define custom formatters to convert `stmt` output to other format types.
- DO NOT manually query series for values unless the user explicitly asks you to.

## External Data

- Connect to or parse data directly from the source. Do not inline data or assumptions into models.
- Avoid network calls inside `spans()` or `point()` to keep code efficient. Prefer to load data upfront.
- Keep secrets in environment variables or local configuration, never in model code.

## Validation and Debugging

Use `Context.deps` to build a cell evaluation graph. Use one-off scripts or an interpreter for quick debugging queries.

Proactively add sensible checks to confirm model correctness (e.g. balance sheet balances, cash roll-forward ties out, etc.).

After creating or editing a model:

- Run the model script or focused tests.
- Print a statement table for a narrow period range.
- Query a few individual lines with `.value(...).eval()` and compare against manual expectations.
- Query at a different cadence from the source spans to test clipping, splitting, and aggregation.
- Check beginning dates, ending dates, missing values, and sign conventions.
- Add or inspect balance sheet checks and other invariant rows.
- Inspect dependency graphs for unexpected circularity or missing dependencies when the model is linked or recursive.
- Use model checks to confirm correctness (e.g. assets = equity + liabilities; cash roll-forward sums correctly, etc).
- Keep signs consistent with the surrounding model. The Orcaset examples generally use revenue, assets, and inflows as positive, and expenses, outflows, capex, and taxes as negative.
