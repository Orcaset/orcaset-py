# Statements and outputs

Build statements using the `stmt` module and format statements using the `formatter` module (or a custom formatter if needed). Keep imports only used for outputs, report dates/periods, context creation, formatting, and file writes in the output layer described in [core.md](core.md). Reporting periods/dates should always be defined in the output section, NEVER in the model section/files.

## Statement structure

Use `orcaset.stmt` to arrange line items and `orcaset.formatter` to render the resolved result.

| Construct | Purpose |
|---|---|
| `stmt.Stmt(*items)` | Ordered collection of series, totals, and groups |
| `stmt.Total(series, items)` | Display an existing total series below its component rows |
| `stmt.Group(*items, label=None)` | Group rows under an optional label without calculating a total |

`Total` does not sum its children or verify that they reconcile. Define the total as a model series, then reference that same series in the statement. Nest totals to show intermediate subtotals. Row names come from the underlying series `name` attribute. Group labels describe sections.

This complete example reports two historical monthly observations:

```py
from datetime import date

from orcaset import Period, Series, ops, period_union, query

january = Period(date(2025, 12, 31), date(2026, 1, 31))
february = Period(date(2026, 1, 31), date(2026, 2, 28))
revenue = Series.of(
    "Revenue", query.covered, pairs=[(january, 100.0), (february, 120.0)]
)
costs = ops.scale("Costs", revenue, -0.4)
profit = ops.add("Profit", revenue, costs, merge_keys=period_union)


if __name__ == "__main__":
    from orcaset import Context, formatter, stmt

    ctx = Context()
    periods = Period.list(date(2025, 12, 31), relativedelta(years=1), date(2026, 2, 28))
    statement = stmt.Stmt(
        stmt.Group(stmt.Total(profit, [revenue, costs]), label="Operating results")
    )
    result = statement.values_for_periods(ctx, periods)
    print(formatter.fixed_width_table(result))
```

For recurring report intervals, create a bounded `Period.list(start, offset, end)` or take a finite slice of `Period.seq(...)`. Keep the report periods in chronological order.

## Periods, dates, and query behavior

`statement.values_for_periods(ctx, periods)` returns a `stmt.StatementResult` containing nested rows, the requested periods, and their unique sorted boundary dates. `statement.values(ctx, periods)` is an alias.

- A period-keyed series is queried at each requested `Period`. A series' query policy determines how to interpolate and aggregate values when query periods do not align with underlying period boundaries.
- A date-keyed series is queried at every distinct start and end date in the requested periods. Built-in tables align these values to an initial-date column and the period-end columns. Use this to show a single balance series at opening and closing dates.

Use contiguous periods for mixed balance-and-flow tables. A gap can introduce a start date that is neither the first start nor another period's end, so its date-keyed value has no table column and the formatter raises `ValueError`.

`statement.values_for_dates(ctx, dates)` queries date-keyed series at the requested dates, deduplicated in input order. Period-keyed rows have `None` values in this view; they are not converted to point-in-time values. The built-in table formatters require a nonempty period-based result, so render a dates-only result with a custom exporter.

## Formats and missing values

`formatter.fixed_width_table`, `formatter.markdown_table`, and `formatter.csv_table` return strings. Each accepts `date_formatter: Callable[[date], str]` and `value_formatter: Callable[[float | None], str]`. Fixed-width and Markdown tables also accept `indent`; fixed-width tables accept `padding`.

The defaults use ISO dates, two decimal places with thousands separators, and a blank for missing values. Model `Na` values become `None` in statement results. Preserve the distinction between missing values and genuine zeroes; use an explicit missing-value label when blanks could mislead.

Add the following inside the example's existing `__main__` block to write CSV using a format suitable for numeric consumers:

```py
from pathlib import Path


def csv_number(value: float | None) -> str:
    return "" if value is None else str(value)


Path("statement.csv").write_text(
    formatter.csv_table(result, value_formatter=csv_number) + "\n",
    encoding="utf-8",
)
print(formatter.markdown_table(result))
```

The built-in CSV is a presentation table with two header rows, section labels, and subtotals. For a machine-oriented dataset, traverse the structured result or query the public series and write explicit fields such as line item, period start, period end, date, value, and unit. Do not parse a formatted table back into model inputs.

One value formatter applies to the whole table and receives no row identity. Use separate statements or a custom renderer when amounts, percentages, and multiples need different formats. State the currency, scale, percentage convention, and sign convention in the surrounding report. Round for display, not in the model calculations.

## Custom values and standalone metrics

Statement values are converted with `float(value)`; `Na` and `None` become `None`. Citation-bearing float subclasses therefore lose their attached metadata in the resolved statement. Unit wrappers without `__float__` cannot be rendered directly. Extract a numeric reporting view explicitly, or use a custom exporter that preserves units and source fields. See [values.md](values.md) for the underlying value patterns.

`Stmt` accepts series, totals, and groups. Resolve standalone metrics such as IRR or MOIC with `ctx.get(metric)` and format them separately; do NOT fabricate a time series just to put a scalar into a table. For custom exports, inspect `LineRow`, `TotalRow`, and `GroupRow`, then `PeriodValue` or `DateValue` within their values. Groups contain children; totals contain both their own values and children.

Before delivering a report, apply [verification.md](verification.md), inspect the rendered dates and signs, and confirm that displayed totals use the verified model nodes.
