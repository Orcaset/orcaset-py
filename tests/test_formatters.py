from datetime import date

import pytest

from orcaset import (
    DateValue,
    GroupRow,
    LineRow,
    Period,
    PeriodValue,
    Series,
    StatementResult,
    TotalRow,
    csv_table,
    exact,
    fixed_width_table,
    markdown_table,
)

P1 = Period(date(2026, 1, 1), date(2026, 4, 1))
P2 = Period(date(2026, 4, 1), date(2026, 7, 1))

A = Series.of("A", exact, [])
B = Series.of("B", exact, [])
C = Series.of("C", exact, [])


def test_fixed_width_table_formats_period_and_date_values():
    result = StatementResult(
        rows=(
            LineRow("Revenue", A, (PeriodValue(P1, 1.0), PeriodValue(P2, 2.0))),
            LineRow(
                "Cash",
                B,
                (
                    DateValue(date(2026, 1, 1), 10.0),
                    DateValue(date(2026, 4, 1), 20.0),
                    DateValue(date(2026, 7, 1), 30.0),
                ),
            ),
        ),
        periods=(P1, P2),
        dates=(date(2026, 1, 1), date(2026, 4, 1), date(2026, 7, 1)),
    )

    assert fixed_width_table(result) == "Start                2026-01-01  2026-04-01\nEnd      2026-01-01  2026-04-01  2026-07-01\nRevenue                    1.00        2.00\nCash          10.00       20.00       30.00"


def test_fixed_width_table_formats_totals_groups_and_indentation():
    result = StatementResult(
        rows=(
            LineRow("A", A, (PeriodValue(P1, 1.0), PeriodValue(P2, 2.0))),
            TotalRow(
                "Total",
                A,
                (PeriodValue(P1, 3.0), PeriodValue(P2, 4.0)),
                (LineRow("B", B, (PeriodValue(P1, 5.0), PeriodValue(P2, None))),),
            ),
            GroupRow((LineRow("C", C, (PeriodValue(P1, 8.0), PeriodValue(P2, 9.0))),)),
        ),
        periods=(P1, P2),
        dates=(),
    )

    assert fixed_width_table(result, date_formatter=lambda dt: dt.strftime("%m/%d")) == "Start         01/01  04/01\nEnd    01/01  04/01  07/01\nA              1.00   2.00\n  B            5.00\n--------------------------\nTotal          3.00   4.00\n\n  C            8.00   9.00\n"


def test_fixed_width_table_allows_custom_value_formatting():
    result = StatementResult(
        rows=(LineRow("A", A, (PeriodValue(P1, 1.25), PeriodValue(P2, None))),),
        periods=(P1, P2),
        dates=(),
    )

    assert fixed_width_table(
        result,
        date_formatter=lambda dt: dt.strftime("%m/%d"),
        value_formatter=lambda value: "-" if value is None else f"{value:.1f}x",
    ) == "Start         01/01  04/01\nEnd    01/01  04/01  07/01\nA              1.2x      -"


def test_csv_table_formats_totals_groups_and_escapes_values_without_indentation():
    result = StatementResult(
        rows=(
            LineRow("A", A, (PeriodValue(P1, 1.0), PeriodValue(P2, 2.0))),
            TotalRow(
                "Total",
                A,
                (PeriodValue(P1, 3.0), PeriodValue(P2, 4.0)),
                (LineRow("B", B, (PeriodValue(P1, 1234.0), PeriodValue(P2, None))),),
            ),
            GroupRow((LineRow("C", C, (PeriodValue(P1, 8.0), PeriodValue(P2, 9.0))),)),
        ),
        periods=(P1, P2),
        dates=(),
    )

    assert csv_table(
        result,
        date_formatter=lambda dt: dt.strftime("%b %d, %Y"),
    ) == 'Start,,"Jan 01, 2026","Apr 01, 2026"\nEnd,"Jan 01, 2026","Apr 01, 2026","Jul 01, 2026"\nA,,1.00,2.00\nB,,"1,234.00",\nTotal,,3.00,4.00\n\nC,,8.00,9.00\n'


def test_csv_table_allows_custom_value_formatting():
    result = StatementResult(
        rows=(LineRow("A", A, (PeriodValue(P1, 1.25), PeriodValue(P2, None))),),
        periods=(P1, P2),
        dates=(),
    )

    assert csv_table(
        result,
        date_formatter=lambda dt: dt.strftime("%m/%d"),
        value_formatter=lambda value: "-" if value is None else f"{value:.1f}x",
    ) == "Start,,01/01,04/01\nEnd,01/01,04/01,07/01\nA,,1.2x,-"


def test_markdown_table_formats_totals_groups_indentation_and_escapes_cells():
    result = StatementResult(
        rows=(
            LineRow("A", A, (PeriodValue(P1, 1.0), PeriodValue(P2, 2.0))),
            TotalRow(
                "Total",
                A,
                (PeriodValue(P1, 3.0), PeriodValue(P2, 4.0)),
                (LineRow("B", B, (PeriodValue(P1, 5.0), PeriodValue(P2, None))),),
            ),
            GroupRow((LineRow("C", C, (PeriodValue(P1, 8.0), PeriodValue(P2, 9.0))),)),
        ),
        periods=(P1, P2),
        dates=(),
    )

    assert markdown_table(result, date_formatter=lambda dt: dt.strftime("%m/%d")) == "| Start |  | 01/01 | 04/01 |\n| --- | ---: | ---: | ---: |\n| End | 01/01 | 04/01 | 07/01 |\n| A |  | 1.00 | 2.00 |\n| &nbsp;&nbsp;B |  | 5.00 |  |\n| **Total** |  | **3.00** | **4.00** |\n|  |  |  |  |\n| &nbsp;&nbsp;C |  | 8.00 | 9.00 |\n|  |  |  |  |"


def test_markdown_table_allows_custom_value_formatting():
    result = StatementResult(
        rows=(LineRow("A", A, (PeriodValue(P1, 1.25), PeriodValue(P2, None))),),
        periods=(P1, P2),
        dates=(),
    )

    assert markdown_table(
        result,
        date_formatter=lambda dt: dt.strftime("%m/%d"),
        value_formatter=lambda value: "-" if value is None else f"{value:.1f}x",
    ) == "| Start |  | 01/01 | 04/01 |\n| --- | ---: | ---: | ---: |\n| End | 01/01 | 04/01 | 07/01 |\n| A |  | 1.2x | - |"


def test_fixed_width_table_rejects_date_values_that_do_not_align_to_period_boundaries():
    result = StatementResult(
        rows=(LineRow("Cash", B, (DateValue(date(2026, 2, 1), 10.0),)),),
        periods=(P1, P2),
        dates=(date(2026, 2, 1),),
    )

    with pytest.raises(ValueError, match="does not align"):
        fixed_width_table(result)


def test_csv_table_rejects_date_values_that_do_not_align_to_period_boundaries():
    result = StatementResult(
        rows=(LineRow("Cash", B, (DateValue(date(2026, 2, 1), 10.0),)),),
        periods=(P1, P2),
        dates=(date(2026, 2, 1),),
    )

    with pytest.raises(ValueError, match="does not align"):
        csv_table(result)


def test_markdown_table_rejects_date_values_that_do_not_align_to_period_boundaries():
    result = StatementResult(
        rows=(LineRow("Cash", B, (DateValue(date(2026, 2, 1), 10.0),)),),
        periods=(P1, P2),
        dates=(date(2026, 2, 1),),
    )

    with pytest.raises(ValueError, match="does not align"):
        markdown_table(result)


def test_fixed_width_table_requires_period_result():
    result = StatementResult(
        rows=(LineRow("Cash", B, (DateValue(date(2026, 1, 1), 10.0),)),),
        periods=(),
        dates=(date(2026, 1, 1),),
    )

    with pytest.raises(ValueError, match="requires .* periods"):
        fixed_width_table(result)


def test_csv_table_requires_period_result():
    result = StatementResult(
        rows=(LineRow("Cash", B, (DateValue(date(2026, 1, 1), 10.0),)),),
        periods=(),
        dates=(date(2026, 1, 1),),
    )

    with pytest.raises(ValueError, match="requires .* periods"):
        csv_table(result)


def test_markdown_table_requires_period_result():
    result = StatementResult(
        rows=(LineRow("Cash", B, (DateValue(date(2026, 1, 1), 10.0),)),),
        periods=(),
        dates=(date(2026, 1, 1),),
    )

    with pytest.raises(ValueError, match="requires .* periods"):
        markdown_table(result)
