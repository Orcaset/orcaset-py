"""Format ``StatementResult`` values as a simple black-and-white HTML table.

Mirrors the layout of ``orcaset.formatter.fixed_width_table``: group spacing,
indentation, and total rules are retained so the output reads like a standard
financial statement.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from html import escape

from orcaset.formatter import DateFormatter, ValueFormatter
from orcaset.period import Period
from orcaset.stmt import (
    DateValue,
    GroupRow,
    LineRow,
    PeriodValue,
    StatementResult,
    StmtRow,
    StmtValue,
    TotalRow,
)

__all__ = ["html_table"]

type _TableColumn = _InitialDateColumn | _PeriodColumn
type _ColumnKey = date | Period

_STYLE = """\
<style>
table.stmt { border-collapse: collapse; font-family: Georgia, "Times New Roman", serif;
             color: #000; background: #fff; }
table.stmt th, table.stmt td { font-weight: normal; padding: 1px 12px 1px 0; }
table.stmt thead th { font-weight: bold; border-bottom: 1px solid #000; }
table.stmt td.num, table.stmt th.num { text-align: right; padding-left: 18px; }
table.stmt tr.spacer td { padding: 0; font-size: 0.45em; }
table.stmt tr.total td { border-top: 1px solid #000; font-weight: bold; }
table.stmt tr.group-label td { font-weight: bold; }
</style>"""


def html_table(
    result: StatementResult,
    *,
    title: str | None = None,
    date_formatter: DateFormatter | None = None,
    value_formatter: ValueFormatter | None = None,
    indent: int = 2,
) -> str:
    """
    Format a period-based statement result as a complete HTML document.

    Declares UTF-8 in ``<head>`` so typographic punctuation in titles and labels
    (em dashes, en dashes) is not misread as Windows-1252. Date-keyed values
    align to the initial period start or to period end dates. Raises
    ``ValueError`` if the result has no periods or contains date values at other
    dates.
    """
    if not result.periods:
        raise ValueError("html_table requires a statement result with periods")

    date_format = date_formatter or _format_date
    value_format = value_formatter or _format_value
    columns = _period_columns(result.periods)
    column_count = len(columns) + 1
    escaped_title = escape(title) if title is not None else "Statement"

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{escaped_title}</title>",
        _STYLE,
        "</head>",
        "<body>",
    ]
    if title is not None:
        parts.append(f"<h1>{escaped_title}</h1>")
    parts.extend(
        [
            '<table class="stmt">',
            "<thead>",
            _header_row("Start", columns, date_format, start=True),
            _header_row("End", columns, date_format, start=False),
            "</thead>",
            "<tbody>",
        ]
    )
    parts.extend(_render_rows(result.rows, columns, value_format, indent, column_count))
    parts.append("</tbody>")
    parts.append("</table>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


class _InitialDateColumn:
    def __init__(self, date: date) -> None:
        self.date = date


class _PeriodColumn:
    def __init__(self, period: Period) -> None:
        self.period = period


def _period_columns(periods: Sequence[Period]) -> tuple[_TableColumn, ...]:
    return (
        _InitialDateColumn(periods[0].start),
        *(_PeriodColumn(period) for period in periods),
    )


def _header_row(
    title: str,
    columns: Sequence[_TableColumn],
    date_formatter: DateFormatter,
    *,
    start: bool,
) -> str:
    cells = [f'<th class="label">{escape(title)}</th>']
    for column in columns:
        if start:
            value = "" if isinstance(column, _InitialDateColumn) else date_formatter(column.period.start)
        else:
            value = date_formatter(
                column.date if isinstance(column, _InitialDateColumn) else column.period.end
            )
        cells.append(f'<th class="num">{escape(value)}</th>')
    return f"<tr>{''.join(cells)}</tr>"


def _render_rows(
    rows: Sequence[StmtRow],
    columns: Sequence[_TableColumn],
    value_formatter: ValueFormatter,
    indent: int,
    column_count: int,
    level: int = 0,
) -> list[str]:
    rendered: list[str] = []
    for row in rows:
        if isinstance(row, LineRow):
            rendered.append(_value_row(row.name, row.values, columns, value_formatter, indent, level))
        elif isinstance(row, TotalRow):
            rendered.extend(
                _render_rows(row.children, columns, value_formatter, indent, column_count, level + 1)
            )
            rendered.append(
                _value_row(
                    row.name, row.values, columns, value_formatter, indent, level, css_class="total"
                )
            )
        elif isinstance(row, GroupRow):
            rendered.append(_spacer_row(column_count))
            if row.label is not None:
                rendered.append(_label_row(row.label, columns, indent, level))
            rendered.extend(
                _render_rows(row.children, columns, value_formatter, indent, column_count, level + 1)
            )
            rendered.append(_spacer_row(column_count))
    return rendered


def _spacer_row(column_count: int) -> str:
    return f'<tr class="spacer"><td colspan="{column_count}">&nbsp;</td></tr>'


def _value_row(
    name: str,
    values: Sequence[StmtValue],
    columns: Sequence[_TableColumn],
    value_formatter: ValueFormatter,
    indent: int,
    level: int,
    *,
    css_class: str = "line",
) -> str:
    values_by_column = _values_by_column(values, columns)
    cells = [
        f'<td class="label" style="padding-left:{indent * level}ch">{escape(name)}</td>',
        *(
            f'<td class="num">{escape(value_formatter(values_by_column.get(_column_key(column))))}</td>'
            for column in columns
        ),
    ]
    return f'<tr class="{css_class}">{"".join(cells)}</tr>'


def _label_row(
    name: str,
    columns: Sequence[_TableColumn],
    indent: int,
    level: int,
) -> str:
    cells = [
        f'<td class="label" style="padding-left:{indent * level}ch">{escape(name)}</td>',
        *(f'<td class="num"></td>' for _ in columns),
    ]
    return f'<tr class="group-label">{"".join(cells)}</tr>'


def _values_by_column(
    values: Sequence[StmtValue],
    columns: Sequence[_TableColumn],
) -> Mapping[_ColumnKey, float | None]:
    valid_keys = {_column_key(column) for column in columns}
    mapped: dict[_ColumnKey, float | None] = {}

    for value in values:
        key = _value_key(value, columns)
        if key not in valid_keys:
            raise ValueError(f"Statement value does not align to a table column: {value!r}")
        mapped[key] = value.value

    return mapped


def _value_key(value: StmtValue, columns: Sequence[_TableColumn]) -> _ColumnKey:
    if isinstance(value, PeriodValue):
        return value.period
    if isinstance(value, DateValue):
        return _date_key(value.date, columns)

    raise TypeError(f"Unsupported statement value: {value!r}")


def _date_key(dt: date, columns: Sequence[_TableColumn]) -> _ColumnKey:
    for column in columns:
        if isinstance(column, _InitialDateColumn) and column.date == dt:
            return column.date
        if isinstance(column, _PeriodColumn) and column.period.end == dt:
            return column.period
    return dt


def _column_key(column: _TableColumn) -> _ColumnKey:
    if isinstance(column, _InitialDateColumn):
        return column.date
    return column.period


def _format_value(value: float | None) -> str:
    return "" if value is None else f"{value:,.2f}"


def _format_date(dt: date) -> str:
    return dt.isoformat()
