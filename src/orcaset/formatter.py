# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

"""Format ``StatementResult`` values as fixed-width, CSV, or Markdown tables."""

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from io import StringIO
from typing import Any

from orcaset.maybe import isna
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

__all__ = [
    "DateFormatter",
    "TypeFormatters",
    "ValueFormatter",
    "csv_table",
    "fixed_width_table",
    "format_value",
    "markdown_table",
]

type ValueFormatter = Callable[[float | None], str]
type TypeFormatters = Mapping[type[Any], Callable[[Any], str]]
type DateFormatter = Callable[[date], str]
type _CellFormatter = Callable[[object], str]
type _RenderedRow = tuple[str, ...] | _HorizontalRule | _Spacer


def fixed_width_table(
    result: StatementResult,
    *,
    date_formatter: DateFormatter | None = None,
    value_formatter: ValueFormatter | None = None,
    type_formatters: TypeFormatters | None = None,
    indent: int = 2,
    padding: int = 2,
) -> str:
    """
    Format a statement result as a fixed-width table.

    Each key in ``result.keys`` is one value column, in order. A period column's
    headers are its start and end; a date column has a blank start and the date
    as its end. Each value lands in the column matching its ``key``; a column
    with no value is blank. Cells are printed with ``format_value``. Raises
    ``ValueError`` if a value's key is not in ``result.keys``.
    """
    table = _render_table(result, date_formatter, value_formatter, type_formatters, indent)
    widths = _column_widths(table)

    lines = [
        _format_line(table.start_header, widths, padding),
        _format_line(table.end_header, widths, padding),
    ]

    for row in table.rows:
        if isinstance(row, _Spacer):
            lines.append("")
            continue
        if isinstance(row, _HorizontalRule):
            lines.append(_horizontal_line(widths, padding))
            continue
        lines.append(_format_line(row, widths, padding))

    return "\n".join(lines)


def csv_table(
    result: StatementResult,
    *,
    date_formatter: DateFormatter | None = None,
    value_formatter: ValueFormatter | None = None,
    type_formatters: TypeFormatters | None = None,
) -> str:
    """
    Format a statement result as CSV.

    Each key in ``result.keys`` is one value column, in order. A period column's
    headers are its start and end; a date column has a blank start and the date
    as its end. Each value lands in the column matching its ``key``; a column
    with no value is blank. Cells are printed with ``format_value``. Raises
    ``ValueError`` if a value's key is not in ``result.keys``.
    """
    table = _render_table(result, date_formatter, value_formatter, type_formatters, 0)

    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(table.start_header)
    writer.writerow(table.end_header)

    for row in table.rows:
        if isinstance(row, _Spacer):
            writer.writerow(())
            continue
        if isinstance(row, _HorizontalRule):
            continue
        writer.writerow(row)

    return output.getvalue().removesuffix("\n")


def markdown_table(
    result: StatementResult,
    *,
    date_formatter: DateFormatter | None = None,
    value_formatter: ValueFormatter | None = None,
    type_formatters: TypeFormatters | None = None,
    indent: int = 2,
) -> str:
    """
    Format a statement result as a Markdown table.

    Each key in ``result.keys`` is one value column, in order. A period column's
    headers are its start and end; a date column has a blank start and the date
    as its end. Each value lands in the column matching its ``key``; a column
    with no value is blank. Cells are printed with ``format_value``. Raises
    ``ValueError`` if a value's key is not in ``result.keys``.
    """
    table = _render_table(result, date_formatter, value_formatter, type_formatters, indent)
    column_count = len(_column_widths(table))

    lines = [
        _markdown_line(table.start_header, column_count),
        _markdown_separator(column_count),
        _markdown_line(table.end_header, column_count),
    ]

    bold_next_row = False
    for row in table.rows:
        if isinstance(row, _Spacer):
            lines.append(_markdown_line((), column_count))
            continue
        if isinstance(row, _HorizontalRule):
            bold_next_row = True
            continue
        lines.append(_markdown_line(row, column_count, bold=bold_next_row))
        bold_next_row = False

    return "\n".join(lines)


@dataclass(slots=True)
class _HorizontalRule:
    pass


@dataclass(slots=True)
class _Spacer:
    pass


@dataclass(slots=True)
class _RenderedTable:
    start_header: tuple[str, ...]
    end_header: tuple[str, ...]
    rows: tuple[_RenderedRow, ...]


def _render_table(
    result: StatementResult,
    date_formatter: DateFormatter | None,
    value_formatter: ValueFormatter | None,
    type_formatters: TypeFormatters | None,
    indent: int,
) -> _RenderedTable:
    date_format = date_formatter or _format_date
    columns = result.keys

    def cell_format(value: object) -> str:
        return format_value(
            value, value_formatter=value_formatter, type_formatters=type_formatters
        )

    return _RenderedTable(
        start_header=_start_header(columns, date_format),
        end_header=_end_header(columns, date_format),
        rows=tuple(_render_rows(result.rows, columns, cell_format, indent)),
    )


def _start_header(
    columns: Sequence[StmtKey],
    date_formatter: DateFormatter,
) -> tuple[str, ...]:
    return (
        "Start",
        *(date_formatter(key.start) if isinstance(key, Period) else "" for key in columns),
    )


def _end_header(
    columns: Sequence[StmtKey],
    date_formatter: DateFormatter,
) -> tuple[str, ...]:
    return (
        "End",
        *(date_formatter(key.end if isinstance(key, Period) else key) for key in columns),
    )


def _render_rows(
    rows: Sequence[StmtRow],
    columns: Sequence[StmtKey],
    cell_format: _CellFormatter,
    indent: int,
    level: int = 0,
) -> list[_RenderedRow]:
    rendered: list[_RenderedRow] = []
    for row in rows:
        if isinstance(row, LineRow):
            rendered.append(
                _value_row(row.name, row.values, columns, cell_format, indent, level)
            )
        elif isinstance(row, TotalRow):
            rendered.extend(_render_rows(row.children, columns, cell_format, indent, level + 1))
            rendered.append(_HorizontalRule())
            rendered.append(
                _value_row(row.name, row.values, columns, cell_format, indent, level)
            )
        elif isinstance(row, GroupRow):
            rendered.append(_Spacer())
            if row.label is not None:
                rendered.append(_label_row(row.label, columns, indent, level))
            rendered.extend(_render_rows(row.children, columns, cell_format, indent, level + 1))
            rendered.append(_Spacer())
    return rendered


def _value_row(
    name: str,
    values: Sequence[StmtValue],
    columns: Sequence[StmtKey],
    cell_format: _CellFormatter,
    indent: int,
    level: int,
) -> tuple[str, ...]:
    values_by_key = _values_by_key(values, columns)
    return (
        _label(name, indent, level),
        *(cell_format(values_by_key[key]) if key in values_by_key else "" for key in columns),
    )


def _label_row(
    name: str,
    columns: Sequence[StmtKey],
    indent: int,
    level: int,
) -> tuple[str, ...]:
    return (_label(name, indent, level), *("" for _ in columns))


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


def _label(name: str, indent: int, level: int) -> str:
    return f"{' ' * (indent * level)}{name}"


def _column_widths(table: _RenderedTable) -> tuple[int, ...]:
    column_count = max(
        len(table.start_header),
        len(table.end_header),
        *(len(row) for row in table.rows if isinstance(row, tuple)),
    )
    widths = [0] * column_count

    for row in (table.start_header, table.end_header, *table.rows):
        if not isinstance(row, tuple):
            continue
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    return tuple(widths)


def _format_line(values: Sequence[str], widths: Sequence[int], padding: int) -> str:
    cells: list[str] = []
    for index, width in enumerate(widths):
        value = values[index] if index < len(values) else ""
        if index == 0:
            cells.append(value.ljust(width))
        else:
            cells.append(value.rjust(width))
    return (" " * padding).join(cells).rstrip()


def _horizontal_line(widths: Sequence[int], padding: int) -> str:
    return "-" * (sum(widths) + padding * (len(widths) - 1))


def _markdown_line(values: Sequence[str], column_count: int, *, bold: bool = False) -> str:
    cells = []
    for index in range(column_count):
        value = values[index] if index < len(values) else ""
        cells.append(_markdown_cell(value, bold=bold))
    return f"| {' | '.join(cells)} |"


def _markdown_separator(column_count: int) -> str:
    return f"| {' | '.join(('---', *(('---:',) * (column_count - 1))))} |"


def _markdown_cell(value: str, *, bold: bool) -> str:
    escaped = _escape_markdown_cell(value)
    if bold and escaped:
        return f"**{escaped}**"
    return escaped


def _escape_markdown_cell(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("\n", "<br>")
    )
    leading_spaces = len(escaped) - len(escaped.lstrip(" "))
    if not leading_spaces:
        return escaped
    return f"{'&nbsp;' * leading_spaces}{escaped[leading_spaces:]}"


def format_value(
    value: object,
    *,
    value_formatter: ValueFormatter | None = None,
    type_formatters: TypeFormatters | None = None,
) -> str:
    """
    Format one statement value for display.

    ``None`` and ``Na`` print as ``value_formatter(None)``. Otherwise the first
    match wins: a ``type_formatters`` entry for the value's type or its nearest
    base class, then ``value_formatter(float(value))`` when the type defines
    ``__float__``, then ``str(value)``. ``value_formatter`` defaults to two
    decimal places with thousands separators and a blank for missing values.
    """
    value_format = value_formatter or _format_value
    if value is None or isna(value):
        return value_format(None)
    if type_formatters:
        for cls in type(value).__mro__:
            type_format = type_formatters.get(cls)
            if type_format is not None:
                return type_format(value)
    if hasattr(type(value), "__float__"):
        return value_format(float(value))  # type: ignore[arg-type]
    return str(value)


def _format_value(value: float | None) -> str:
    return "" if value is None else f"{value:,.2f}"


def _format_date(dt: date) -> str:
    return dt.isoformat()
