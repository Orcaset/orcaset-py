"""Format ``StatementResult`` values as a simple black-and-white HTML table.

Mirrors the layout of ``orcaset.formatter.fixed_width_table``: group spacing,
indentation, and total rules are retained so the output reads like a standard
financial statement.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from html import escape

from orcaset.formatter import DateFormatter, TypeFormatters, ValueFormatter, format_value
from orcaset.period import Period
from orcaset.stmt import (
    GroupRow,
    LineRow,
    StatementResult,
    StmtKey,
    StmtRow,
    StmtValue,
    TotalRow,
)

__all__ = ["html_table"]

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
    type_formatters: TypeFormatters | None = None,
    indent: int = 2,
) -> str:
    """
    Format a statement result as a complete HTML document.

    Declares UTF-8 in ``<head>`` so typographic punctuation in titles and labels
    (em dashes, en dashes) is not misread as Windows-1252. Each key in
    ``result.keys`` is one value column; a date column has a blank start header.
    Each value lands in the column matching its ``key`` and is printed with
    ``format_value``. Raises ``ValueError`` if a value's key is not in
    ``result.keys``.
    """
    date_format = date_formatter or _format_date

    def value_format(value: object) -> str:
        return format_value(
            value, value_formatter=value_formatter, type_formatters=type_formatters
        )

    columns = result.keys
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


def _header_row(
    title: str,
    columns: Sequence[StmtKey],
    date_formatter: DateFormatter,
    *,
    start: bool,
) -> str:
    cells = [f'<th class="label">{escape(title)}</th>']
    for key in columns:
        if isinstance(key, Period):
            value = date_formatter(key.start if start else key.end)
        else:
            value = "" if start else date_formatter(key)
        cells.append(f'<th class="num">{escape(value)}</th>')
    return f"<tr>{''.join(cells)}</tr>"


def _render_rows(
    rows: Sequence[StmtRow],
    columns: Sequence[StmtKey],
    value_formatter: Callable[[object], str],
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
    columns: Sequence[StmtKey],
    value_formatter: Callable[[object], str],
    indent: int,
    level: int,
    *,
    css_class: str = "line",
) -> str:
    values_by_key = _values_by_key(values, columns)
    cells = [
        f'<td class="label" style="padding-left:{indent * level}ch">{escape(name)}</td>',
        *(
            f'<td class="num">{escape(value_formatter(values_by_key.get(key)))}</td>'
            for key in columns
        ),
    ]
    return f'<tr class="{css_class}">{"".join(cells)}</tr>'


def _label_row(
    name: str,
    columns: Sequence[StmtKey],
    indent: int,
    level: int,
) -> str:
    cells = [
        f'<td class="label" style="padding-left:{indent * level}ch">{escape(name)}</td>',
        *(f'<td class="num"></td>' for _ in columns),
    ]
    return f'<tr class="group-label">{"".join(cells)}</tr>'


def _values_by_key(
    values: Sequence[StmtValue],
    columns: Sequence[StmtKey],
) -> Mapping[StmtKey, object]:
    valid_keys = set(columns)
    mapped: dict[StmtKey, object] = {}

    for value in values:
        if value.key not in valid_keys:
            raise ValueError(f"Statement value does not align to a table column: {value!r}")
        mapped[value.key] = value.value

    return mapped


def _format_date(dt: date) -> str:
    return dt.isoformat()
