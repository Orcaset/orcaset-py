from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import pytest

import orcaset
from orcaset import Period, Series, formatter, stmt
from orcaset.maybe import Na
from orcaset.query import exact

P1 = Period(date(2026, 1, 1), date(2026, 4, 1))
P2 = Period(date(2026, 4, 1), date(2026, 7, 1))

A = Series.of("A", exact, [])
B = Series.of("B", exact, [])
C = Series.of("C", exact, [])


def cell(key: stmt.StmtKey, value: object) -> stmt.StmtValue:
    return stmt.StmtValue(key=key, series=A, query=key, value=value)


def test_formatter_helpers_are_exported_only_from_formatter_module():
    names = {
        "DateFormatter",
        "TypeFormatters",
        "ValueFormatter",
        "csv_table",
        "fixed_width_table",
        "format_value",
        "markdown_table",
    }

    assert set(orcaset.formatter.__all__) == names
    assert all(not hasattr(orcaset, name) for name in names)


def test_fixed_width_table_formats_one_column_per_period():
    result = stmt.StatementResult(
        rows=(
            stmt.LineRow("Revenue", A, (cell(P1, 1.0), cell(P2, 2.0))),
            stmt.LineRow("Cash", B, (cell(P1, 20.0), cell(P2, 30.0))),
        ),
        keys=(P1, P2),
    )

    assert (
        formatter.fixed_width_table(result)
        == "Start    2026-01-01  2026-04-01\nEnd      2026-04-01  2026-07-01\nRevenue        1.00        2.00\nCash          20.00       30.00"
    )


def test_fixed_width_table_aligns_values_by_key_for_unordered_overlapping_periods():
    h1 = Period(date(2026, 1, 1), date(2026, 7, 1))
    result = stmt.StatementResult(
        rows=(
            stmt.LineRow(
                "A",
                A,
                (cell(h1, 3.0), cell(P1, 1.0), cell(P2, 2.0)),
            ),
        ),
        keys=(P2, P1, h1),
    )

    assert (
        formatter.fixed_width_table(result, date_formatter=lambda dt: dt.strftime("%m/%d"))
        == "Start  04/01  01/01  01/01\nEnd    07/01  04/01  07/01\nA       2.00   1.00   3.00"
    )


def test_tables_render_date_keys_as_columns_with_blank_start():
    opening = date(2026, 1, 1)
    result = stmt.StatementResult(
        rows=(
            stmt.LineRow(
                "Cash",
                B,
                (cell(opening, 10.0), cell(P1, 20.0), cell(P2, 30.0)),
            ),
            stmt.LineRow(
                "Revenue",
                A,
                (cell(opening, None), cell(P1, 1.0), cell(P2, 2.0)),
            ),
        ),
        keys=(opening, P1, P2),
    )

    def date_format(dt: date) -> str:
        return dt.strftime("%m/%d")

    assert (
        formatter.fixed_width_table(result, date_formatter=date_format)
        == "Start           01/01  04/01\nEnd      01/01  04/01  07/01\nCash     10.00  20.00  30.00\nRevenue          1.00   2.00"
    )
    assert (
        formatter.csv_table(result, date_formatter=date_format)
        == "Start,,01/01,04/01\nEnd,01/01,04/01,07/01\nCash,10.00,20.00,30.00\nRevenue,,1.00,2.00"
    )
    assert (
        formatter.markdown_table(result, date_formatter=date_format)
        == "| Start |  | 01/01 | 04/01 |\n| --- | ---: | ---: | ---: |\n| End | 01/01 | 04/01 | 07/01 |\n| Cash | 10.00 | 20.00 | 30.00 |\n| Revenue |  | 1.00 | 2.00 |"
    )


def test_statement_result_splits_keys_into_periods_and_dates_in_order():
    opening = date(2026, 1, 1)
    result = stmt.StatementResult(rows=(), keys=(P2, opening, P1))

    assert result.periods == (P2, P1)
    assert result.dates == (opening,)


def test_fixed_width_table_formats_totals_groups_and_indentation():
    result = stmt.StatementResult(
        rows=(
            stmt.LineRow("A", A, (cell(P1, 1.0), cell(P2, 2.0))),
            stmt.TotalRow(
                "Total",
                A,
                (cell(P1, 3.0), cell(P2, 4.0)),
                (stmt.LineRow("B", B, (cell(P1, 5.0), cell(P2, None))),),
            ),
            stmt.GroupRow(None, (stmt.LineRow("C", C, (cell(P1, 8.0), cell(P2, 9.0))),)),
        ),
        keys=(P1, P2),
    )

    assert (
        formatter.fixed_width_table(result, date_formatter=lambda dt: dt.strftime("%m/%d"))
        == "Start  01/01  04/01\nEnd    04/01  07/01\nA       1.00   2.00\n  B     5.00\n-------------------\nTotal   3.00   4.00\n\n  C     8.00   9.00\n"
    )


def test_fixed_width_table_allows_custom_value_formatting():
    result = stmt.StatementResult(
        rows=(stmt.LineRow("A", A, (cell(P1, 1.25), cell(P2, None))),),
        keys=(P1, P2),
    )

    assert (
        formatter.fixed_width_table(
            result,
            date_formatter=lambda dt: dt.strftime("%m/%d"),
            value_formatter=lambda value: "-" if value is None else f"{value:.1f}x",
        )
        == "Start  01/01  04/01\nEnd    04/01  07/01\nA       1.2x      -"
    )


def test_csv_table_formats_totals_groups_and_escapes_values_without_indentation():
    result = stmt.StatementResult(
        rows=(
            stmt.LineRow("A", A, (cell(P1, 1.0), cell(P2, 2.0))),
            stmt.TotalRow(
                "Total",
                A,
                (cell(P1, 3.0), cell(P2, 4.0)),
                (stmt.LineRow("B", B, (cell(P1, 1234.0), cell(P2, None))),),
            ),
            stmt.GroupRow(None, (stmt.LineRow("C", C, (cell(P1, 8.0), cell(P2, 9.0))),)),
        ),
        keys=(P1, P2),
    )

    assert (
        formatter.csv_table(
            result,
            date_formatter=lambda dt: dt.strftime("%b %d, %Y"),
        )
        == 'Start,"Jan 01, 2026","Apr 01, 2026"\nEnd,"Apr 01, 2026","Jul 01, 2026"\nA,1.00,2.00\nB,"1,234.00",\nTotal,3.00,4.00\n\nC,8.00,9.00\n'
    )


def test_csv_table_allows_custom_value_formatting():
    result = stmt.StatementResult(
        rows=(stmt.LineRow("A", A, (cell(P1, 1.25), cell(P2, None))),),
        keys=(P1, P2),
    )

    assert (
        formatter.csv_table(
            result,
            date_formatter=lambda dt: dt.strftime("%m/%d"),
            value_formatter=lambda value: "-" if value is None else f"{value:.1f}x",
        )
        == "Start,01/01,04/01\nEnd,04/01,07/01\nA,1.2x,-"
    )


def test_markdown_table_formats_totals_groups_indentation_and_escapes_cells():
    result = stmt.StatementResult(
        rows=(
            stmt.LineRow("A", A, (cell(P1, 1.0), cell(P2, 2.0))),
            stmt.TotalRow(
                "Total",
                A,
                (cell(P1, 3.0), cell(P2, 4.0)),
                (stmt.LineRow("B", B, (cell(P1, 5.0), cell(P2, None))),),
            ),
            stmt.GroupRow(None, (stmt.LineRow("C", C, (cell(P1, 8.0), cell(P2, 9.0))),)),
        ),
        keys=(P1, P2),
    )

    assert (
        formatter.markdown_table(result, date_formatter=lambda dt: dt.strftime("%m/%d"))
        == "| Start | 01/01 | 04/01 |\n| --- | ---: | ---: |\n| End | 04/01 | 07/01 |\n| A | 1.00 | 2.00 |\n| &nbsp;&nbsp;B | 5.00 |  |\n| **Total** | **3.00** | **4.00** |\n|  |  |  |\n| &nbsp;&nbsp;C | 8.00 | 9.00 |\n|  |  |  |"
    )


def test_fixed_width_table_prints_group_label_when_present():
    result = stmt.StatementResult(
        rows=(
            stmt.GroupRow(
                "Group",
                (stmt.LineRow("C", C, (cell(P1, 8.0), cell(P2, 9.0))),),
            ),
        ),
        keys=(P1, P2),
    )

    assert (
        formatter.fixed_width_table(result, date_formatter=lambda dt: dt.strftime("%m/%d"))
        == "Start  01/01  04/01\nEnd    04/01  07/01\n\nGroup\n  C     8.00   9.00\n"
    )


def test_csv_table_prints_group_label_when_present():
    result = stmt.StatementResult(
        rows=(
            stmt.GroupRow(
                "Group",
                (stmt.LineRow("C", C, (cell(P1, 8.0), cell(P2, 9.0))),),
            ),
        ),
        keys=(P1, P2),
    )

    assert (
        formatter.csv_table(result, date_formatter=lambda dt: dt.strftime("%m/%d"))
        == "Start,01/01,04/01\nEnd,04/01,07/01\n\nGroup,,\nC,8.00,9.00\n"
    )


def test_markdown_table_prints_group_label_when_present():
    result = stmt.StatementResult(
        rows=(
            stmt.GroupRow(
                "Group",
                (stmt.LineRow("C", C, (cell(P1, 8.0), cell(P2, 9.0))),),
            ),
        ),
        keys=(P1, P2),
    )

    assert (
        formatter.markdown_table(result, date_formatter=lambda dt: dt.strftime("%m/%d"))
        == "| Start | 01/01 | 04/01 |\n| --- | ---: | ---: |\n| End | 04/01 | 07/01 |\n|  |  |  |\n| Group |  |  |\n| &nbsp;&nbsp;C | 8.00 | 9.00 |\n|  |  |  |"
    )


def test_markdown_table_allows_custom_value_formatting():
    result = stmt.StatementResult(
        rows=(stmt.LineRow("A", A, (cell(P1, 1.25), cell(P2, None))),),
        keys=(P1, P2),
    )

    assert (
        formatter.markdown_table(
            result,
            date_formatter=lambda dt: dt.strftime("%m/%d"),
            value_formatter=lambda value: "-" if value is None else f"{value:.1f}x",
        )
        == "| Start | 01/01 | 04/01 |\n| --- | ---: | ---: |\n| End | 04/01 | 07/01 |\n| A | 1.2x | - |"
    )


@pytest.mark.parametrize(
    "render", [formatter.fixed_width_table, formatter.csv_table, formatter.markdown_table]
)
def test_tables_reject_values_whose_key_is_not_a_column(
    render: Callable[[stmt.StatementResult], str],
):
    result = stmt.StatementResult(
        rows=(stmt.LineRow("Cash", B, (cell(date(2026, 4, 1), 10.0),)),),
        keys=(P1, P2),
    )

    with pytest.raises(ValueError, match="does not align"):
        render(result)


def test_fixed_width_table_leaves_columns_without_a_value_blank():
    result = stmt.StatementResult(
        rows=(stmt.LineRow("A", A, (cell(P2, 2.0),)),),
        keys=(P1, P2),
    )

    assert (
        formatter.fixed_width_table(result, date_formatter=lambda dt: dt.strftime("%m/%d"))
        == "Start  01/01  04/01\nEnd    04/01  07/01\nA              2.00"
    )


def test_tables_render_date_only_results():
    result = stmt.StatementResult(
        rows=(
            stmt.LineRow(
                "Cash",
                B,
                (cell(date(2026, 1, 1), 10.0), cell(date(2026, 4, 1), 20.0)),
            ),
        ),
        keys=(date(2026, 1, 1), date(2026, 4, 1)),
    )

    def date_format(dt: date) -> str:
        return dt.strftime("%m/%d")

    assert (
        formatter.fixed_width_table(result, date_formatter=date_format)
        == "Start\nEnd    01/01  04/01\nCash   10.00  20.00"
    )
    assert (
        formatter.csv_table(result, date_formatter=date_format)
        == "Start,,\nEnd,01/01,04/01\nCash,10.00,20.00"
    )
    assert (
        formatter.markdown_table(result, date_formatter=date_format)
        == "| Start |  |  |\n| --- | ---: | ---: |\n| End | 01/01 | 04/01 |\n| Cash | 10.00 | 20.00 |"
    )


def test_format_value_handles_missing_values():
    assert formatter.format_value(None) == ""
    assert formatter.format_value(Na) == ""
    assert formatter.format_value(Na, value_formatter=lambda v: "-" if v is None else str(v)) == "-"


def test_format_value_prefers_type_formatter_then_float_then_str():
    @dataclass(frozen=True)
    class USD:
        amount: float

        def __str__(self) -> str:
            return f"USD {self.amount}"

    class Cited(float):
        pass

    def usd_format(usd: USD) -> str:
        return f"${usd.amount:,.0f}"

    usd_formats = {USD: usd_format}

    assert formatter.format_value(USD(1234.0), type_formatters=usd_formats) == "$1,234"
    assert formatter.format_value(USD(1234.0)) == "USD 1234.0"
    assert formatter.format_value(1234) == "1,234.00"
    assert formatter.format_value(Cited(2.5)) == "2.50"
    assert formatter.format_value(Cited(2.5), type_formatters={float: lambda v: "float"}) == "float"
    assert formatter.format_value("1.5") == "1.5"


def test_tables_format_non_float_values_with_type_formatters():
    @dataclass(frozen=True)
    class USD:
        amount: float

    result = stmt.StatementResult(
        rows=(stmt.LineRow("Revenue", A, (cell(P1, USD(100.0)), cell(P2, Na))),),
        keys=(P1, P2),
    )

    assert (
        formatter.fixed_width_table(
            result,
            date_formatter=lambda dt: dt.strftime("%m/%d"),
            type_formatters={USD: lambda usd: f"${usd.amount:.0f}"},
        )
        == "Start    01/01  04/01\nEnd      04/01  07/01\nRevenue   $100"
    )
