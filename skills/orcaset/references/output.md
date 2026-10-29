# Statements and outputs

Build statements using the `stmt` module and format statements using the `formatter` module (or a custom formatter if needed). Keep imports only used for outputs, report dates/periods, context creation, formatting, and file writes in the output layer described in [core.md](core.md). Reporting periods/dates should always be defined in the output section, NEVER in the model section/files.

## Statement structure

Use `orcaset.stmt` to arrange line items and `orcaset.formatter` to render the resolved result.

| Construct | Purpose |
|---|---|
| `stmt.Stmt(*items, format=None)` | Ordered collection of series, rows, totals, and groups |
| `stmt.Row(series, format=None)` | A line item with its own format |
| `stmt.Total(series, items, format=None)` | Display an existing total series below its component rows |
| `stmt.Group(*items, label=None, format=None)` | Group rows under an optional label without calculating a total |

`Total` does not sum its children or verify that they reconcile. Define the total as a model series, then reference that same series in the statement. Nest totals to show intermediate subtotals. Row names come from the underlying series `name`, which must be given explicitly; `Stmt` rejects a series with a derived name. Group labels describe sections.

This complete example reports two historical monthly observations:

```py
from datetime import date

from orcaset import Period, Series, ops, period_union, query

january = Period(date(2025, 12, 31), date(2026, 1, 31))
february = Period(date(2026, 1, 31), date(2026, 2, 28))
revenue = Series.of(
    query.covered, pairs=[(january, 100.0), (february, 120.0)], name="Revenue"
)
costs = ops.scale(revenue, -0.4, name="Costs")
profit = ops.add(revenue, costs, merge_keys=period_union, name="Profit")


if __name__ == "__main__":
    from dateutil.relativedelta import relativedelta

    from orcaset import Context, formatter, stmt

    ctx = Context()
    periods = Period.list(date(2025, 12, 31), relativedelta(months=1), date(2026, 2, 28))
    statement = stmt.Stmt(
        stmt.Group(stmt.Total(profit, [revenue, costs]), label="Operating results")
    )
    result = statement.values(ctx, periods)
    print(formatter.fixed_width_table(result))
```

For recurring report intervals, create a bounded `Period.list(start, offset, end)` or take a finite slice of `Period.seq(...)`. Columns appear in the order the keys are given.

## Periods, dates, and query behavior

`statement.values(ctx, keys)` takes a sequence of keys, each a `Period` or a `date`, and the two may be mixed. It returns a `stmt.StatementResult` with nested rows. `result.keys` holds the keys in input order, and every `LineRow` and `TotalRow` has one `stmt.StmtValue` per key, in key order. Each value carries its `key`, so match values to keys explicitly rather than by position. `result.periods` and `result.dates` hold the `Period` and `date` keys.

How a series is queried depends on the column key and on the series' own key type:

- At a `Period` key, a period-keyed series is queried at the period. Its query policy determines how to interpolate and aggregate values when query periods do not align with underlying period boundaries.
- At a `Period` key, a date-keyed series is queried at the period's **end**. Periods that share an end both show that closing value. No value is taken at a period's start.
- At a `date` key, a date-keyed series is queried at the date. A period-keyed series is not queried; its value is `Na`, not a point-in-time conversion.

Each `StmtValue` records where it came from: `key` (the column), `series`, `query` (the key the series was queried at, or `None` when not queried), and `value` (the model value unchanged, `Na` on a miss). `ctx.dependencies(value.series, value.query)` traces a cell back through the model.

Keys are not sorted, deduplicated, or checked for contiguity. Out-of-order periods, gaps, overlaps, and nested periods (four quarters followed by their year) are all valid and produce one column each. To show an opening balance, put the opening date before the periods:

```py
result = statement.values(ctx, [periods[0].start, *periods])
```

## Formats and missing values

`formatter.fixed_width_table`, `formatter.markdown_table`, and `formatter.csv_table` return strings. Each key is one value column, in order. A period column's `Start` and `End` headers are that period's start and end dates; a date column has a blank `Start` and the date as `End`. Cells align by key. A dates-only result renders with a blank `Start` row. Each accepts `date_formatter: Callable[[date], str]`, `value_formatter: Callable[[float | None], str]`, and `type_formatters: Mapping[type, Callable[[Any], str]]`. Cells print with `formatter.format_value`: `None` and `Na` go to `value_formatter(None)`; otherwise a `type_formatters` entry for the value's type (or nearest base class) wins, then `value_formatter(float(value))` when the type defines `__float__`, then `str(value)`. Fixed-width and Markdown tables also accept `indent`; fixed-width tables accept `padding`.

A row's own format takes the place of `value_formatter` for that row. Give a format, a `Callable[[float | None], str]`, to a line item with `stmt.Row(series, format=...)`, or to a `Total`, `Group`, or `Stmt` to apply it to every row inside that doesn't set its own; the nearest one wins. Use this to mix units in one statement:

```py
def thousands(value: float | None) -> str:
    return "" if value is None else f"{value / 1000:,.0f}"


def percent(value: float | None) -> str:
    return "" if value is None else f"{value:.1%}"


statement = stmt.Stmt(
    stmt.Total(profit, [revenue, costs]),
    stmt.Row(margin, format=percent),
    format=thousands,
)
```

The defaults use ISO dates, two decimal places with thousands separators, and a blank for missing values. Preserve the distinction between missing values and genuine zeroes; use an explicit missing-value label when blanks could mislead.

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

`StmtValue.value` is the model value unchanged, so citation-bearing float subclasses and unit wrappers keep their metadata for custom exporters. For display, pass `type_formatters` to print a wrapper type (for example `{USD: lambda v: f"${v.amount:,.0f}"}`). Without one, a type defining `__float__` prints as a number and anything else prints with `str()`. See [values.md](values.md) for the underlying value patterns.

`Stmt` accepts series, totals, and groups. Resolve standalone metrics such as IRR or MOIC with `ctx.get(metric)` and format them separately; do NOT fabricate a time series just to put a scalar into a table. For custom exports, inspect `LineRow`, `TotalRow`, and `GroupRow`, then the `StmtValue`s within their values. Groups contain children; totals contain both their own values and children.

Before delivering a report, apply [verification.md](verification.md), inspect the rendered dates and signs, and confirm that displayed totals use the verified model nodes.
