# Copyright (c) 2026 Orcaset Inc.
# SPDX-License-Identifier: SSPL-1.0

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from io import StringIO

from .period import Period
from .stmt import (
    DateValue,
    FamilyLineRow,
    FamilyRow,
    GroupRow,
    LineRow,
    PeriodValue,
    StatementResult,
    StmtRow,
    StmtValue,
    TotalRow,
)


type ValueFormatter = Callable[[float | None], str]
type DateFormatter = Callable[[date], str]
type _TableColumn = _InitialDateColumn | _PeriodColumn
type _ColumnKey = date | Period
type _RenderedRow = tuple[str, ...] | _HorizontalRule | _Spacer


def fixed_width_table(
    result: StatementResult,
    *,
    date_formatter: DateFormatter | None = None,
    value_formatter: ValueFormatter | None = None,
    indent: int = 2,
    padding: int = 2,
) -> str:
    """
    Format a period-based statement result as a fixed-width table.

    Point values align to the initial period start or to period end dates. Raises `ValueError`
    if the result has no periods or contains point values at other dates.
    """
    if not result.periods:
        raise ValueError("fixed_width_table requires a statement result with periods")

    date_format = date_formatter or _format_date
    value_format = value_formatter or _format_value
    columns = _period_columns(result.periods)
    table = _render_table(result.rows, columns, date_format, value_format, indent)
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
) -> str:
    """
    Format a period-based statement result as CSV.

    Point values align to the initial period start or to period end dates. Raises `ValueError`
    if the result has no periods or contains point values at other dates.
    """
    if not result.periods:
        raise ValueError("csv_table requires a statement result with periods")

    date_format = date_formatter or _format_date
    value_format = value_formatter or _format_value
    columns = _period_columns(result.periods)
    table = _render_table(result.rows, columns, date_format, value_format, indent=0)

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
    indent: int = 2,
) -> str:
    """
    Format a period-based statement result as a Markdown table.

    Point values align to the initial period start or to period end dates. Raises `ValueError`
    if the result has no periods or contains point values at other dates.
    """
    if not result.periods:
        raise ValueError("markdown_table requires a statement result with periods")

    date_format = date_formatter or _format_date
    value_format = value_formatter or _format_value
    columns = _period_columns(result.periods)
    table = _render_table(result.rows, columns, date_format, value_format, indent)
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
class _InitialDateColumn:
    date: date


@dataclass(slots=True)
class _PeriodColumn:
    period: Period


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
    rows: Sequence[StmtRow],
    columns: Sequence[_TableColumn],
    date_formatter: DateFormatter,
    value_formatter: ValueFormatter,
    indent: int,
) -> _RenderedTable:
    return _RenderedTable(
        start_header=_start_header(columns, date_formatter),
        end_header=_end_header(columns, date_formatter),
        rows=tuple(_render_rows(rows, columns, value_formatter, indent)),
    )


def _period_columns(periods: Sequence[Period]) -> tuple[_TableColumn, ...]:
    return (
        _InitialDateColumn(periods[0].start),
        *(_PeriodColumn(period) for period in periods),
    )


def _start_header(
    columns: Sequence[_TableColumn],
    date_formatter: DateFormatter,
) -> tuple[str, ...]:
    return (
        "Start",
        *(
            "" if isinstance(column, _InitialDateColumn) else date_formatter(column.period.start)
            for column in columns
        ),
    )


def _end_header(
    columns: Sequence[_TableColumn],
    date_formatter: DateFormatter,
) -> tuple[str, ...]:
    return (
        "End",
        *(
            date_formatter(column.date)
            if isinstance(column, _InitialDateColumn)
            else date_formatter(column.period.end)
            for column in columns
        ),
    )


def _render_rows(
    rows: Sequence[StmtRow],
    columns: Sequence[_TableColumn],
    value_formatter: ValueFormatter,
    indent: int,
    level: int = 0,
) -> list[_RenderedRow]:
    rendered: list[_RenderedRow] = []
    for row in rows:
        if isinstance(row, LineRow | FamilyLineRow):
            rendered.append(
                _value_row(row.name, row.values, columns, value_formatter, indent, level)
            )
        elif isinstance(row, TotalRow):
            rendered.extend(_render_rows(row.children, columns, value_formatter, indent, level + 1))
            rendered.append(_HorizontalRule())
            rendered.append(
                _value_row(row.name, row.values, columns, value_formatter, indent, level)
            )
        elif isinstance(row, FamilyRow):
            rendered.append((_label(row.name, indent, level),))
            rendered.extend(_render_rows(row.children, columns, value_formatter, indent, level + 1))
        elif isinstance(row, GroupRow):
            rendered.append(_Spacer())
            rendered.extend(_render_rows(row.children, columns, value_formatter, indent, level + 1))
            rendered.append(_Spacer())
    return rendered


def _value_row(
    name: str,
    values: Sequence[StmtValue],
    columns: Sequence[_TableColumn],
    value_formatter: ValueFormatter,
    indent: int,
    level: int,
) -> tuple[str, ...]:
    values_by_column = _values_by_column(values, columns)
    return (
        _label(name, indent, level),
        *(
            ""
            if _column_key(column) not in values_by_column
            else value_formatter(values_by_column[_column_key(column)])
            for column in columns
        ),
    )


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


def _format_value(value: float | None) -> str:
    return "" if value is None else f"{value:,.2f}"


def _format_date(dt: date) -> str:
    return dt.isoformat()
