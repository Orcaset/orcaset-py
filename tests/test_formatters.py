from collections.abc import Iterable
from datetime import date

import pytest

from orcaset import (
    DateValue,
    FamilyLineRow,
    FamilyRow,
    GroupRow,
    LineRow,
    Period,
    PeriodValue,
    Span,
    SpanFamilyResult,
    SpanSeries,
    SpanSeriesFamily,
    StatementResult,
    TotalRow,
    fixed_width_table,
    sum_spans,
)

P1 = Period(date(2026, 1, 1), date(2026, 4, 1))
P2 = Period(date(2026, 4, 1), date(2026, 7, 1))


class _TestSpanSeries(SpanSeries):
    @staticmethod
    def agg(spans: list[Span]) -> float | None:
        return sum_spans(0.0)(spans)

    def spans(self) -> Iterable[Span]:
        raise NotImplementedError


class A(_TestSpanSeries):
    def spans(self) -> Iterable[Span]:
        raise NotImplementedError


class B(_TestSpanSeries):
    def spans(self) -> Iterable[Span]:
        raise NotImplementedError


class C(_TestSpanSeries):
    def spans(self) -> Iterable[Span]:
        raise NotImplementedError


class Family(SpanSeriesFamily[str]):
    def spans(self, period: Period) -> SpanFamilyResult[str]:
        return {}


def test_fixed_width_table_formats_period_and_point_values():
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

    assert fixed_width_table(result) == "\n".join(
        [
            "Start                2026-01-01  2026-04-01",
            "End      2026-01-01  2026-04-01  2026-07-01",
            "Revenue                    1.00        2.00",
            "Cash          10.00       20.00       30.00",
        ]
    )


def test_fixed_width_table_formats_totals_groups_and_indentation():
    result = StatementResult(
        rows=(
            LineRow("A", A, (PeriodValue(P1, 1.0), PeriodValue(P2, 2.0))),
            TotalRow(
                "Total",
                A,
                (PeriodValue(P1, 3.0), PeriodValue(P2, 4.0)),
                (
                    LineRow("B", B, (PeriodValue(P1, 5.0), PeriodValue(P2, None))),
                    FamilyRow(
                        "Family",
                        Family,
                        (
                            FamilyLineRow(
                                "Key",
                                Family,
                                "key",
                                (PeriodValue(P1, 6.0), PeriodValue(P2, 7.0)),
                            ),
                        ),
                    ),
                ),
            ),
            GroupRow((LineRow("C", C, (PeriodValue(P1, 8.0), PeriodValue(P2, 9.0))),)),
        ),
        periods=(P1, P2),
        dates=(),
    )

    assert fixed_width_table(result, date_formatter=lambda dt: dt.strftime("%m/%d")) == "\n".join(
        [
            "Start            01/01  04/01",
            "End       01/01  04/01  07/01",
            "A                 1.00   2.00",
            "  B               5.00",
            "  Family",
            "    Key           6.00   7.00",
            "-----------------------------",
            "Total             3.00   4.00",
            "",
            "  C               8.00   9.00",
            "",
        ]
    )


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
    ) == "\n".join(
        [
            "Start         01/01  04/01",
            "End    01/01  04/01  07/01",
            "A              1.2x      -",
        ]
    )


def test_fixed_width_table_rejects_point_values_that_do_not_align_to_period_boundaries():
    result = StatementResult(
        rows=(LineRow("Cash", B, (DateValue(date(2026, 2, 1), 10.0),)),),
        periods=(P1, P2),
        dates=(date(2026, 2, 1),),
    )

    with pytest.raises(ValueError, match="does not align"):
        fixed_width_table(result)


def test_fixed_width_table_requires_period_result():
    result = StatementResult(
        rows=(LineRow("Cash", B, (DateValue(date(2026, 1, 1), 10.0),)),),
        periods=(),
        dates=(date(2026, 1, 1),),
    )

    with pytest.raises(ValueError, match="requires .* periods"):
        fixed_width_table(result)
