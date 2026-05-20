from datetime import date

import pytest

from orcaset import (
    Context,
    FamilyLineRow,
    FamilyRow,
    Formula,
    Group,
    GroupRow,
    LineRow,
    Period,
    Span,
    SpanFamilyResult,
    SpanSeriesFamily,
    Stmt,
    Total,
    TotalRow,
    no_split,
    span,
    sum_spans,
)


def test_stmt_values_uses_series_class_name_for_line_items():
    Revenue = span.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), 100.0),
            ((date(2025, 2, 1), date(2025, 3, 1)), 200.0),
        ],
        name="Revenue",
    )

    ctx = Context()
    rows = Stmt(Revenue).values(
        ctx,
        [
            Period(date(2025, 1, 1), date(2025, 2, 1)),
            Period(date(2025, 2, 1), date(2025, 3, 1)),
        ],
    )

    assert len(rows) == 1
    assert isinstance(rows[0], LineRow)
    assert rows[0].name == "Revenue"
    assert rows[0].series is Revenue
    assert rows[0].values == (100.0, 200.0)


def test_stmt_values_prefers_series_label_for_line_items():
    Revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        name="Revenue",
    )
    Revenue.label = "Net Revenue"

    ctx = Context()
    rows = Stmt(Revenue).values(
        ctx,
        [Period(date(2025, 1, 1), date(2025, 2, 1))],
    )

    assert len(rows) == 1
    assert isinstance(rows[0], LineRow)
    assert rows[0].name == "Net Revenue"


def test_stmt_total_uses_real_series_and_nests_children():
    Revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        name="Revenue",
    )
    Costs = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 40.0)],
        name="Costs",
    )
    Income = span.sub(Revenue, Costs)

    ctx = Context()
    rows = Stmt(Total(Income, [Revenue, Costs])).values(
        ctx,
        [Period(date(2025, 1, 1), date(2025, 2, 1))],
    )

    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, TotalRow)
    assert row.name == "SubRevenueCosts"
    assert row.series is Income
    assert row.values == (60.0,)
    children = [child for child in row.children if isinstance(child, LineRow)]
    assert len(children) == 2
    assert [child.name for child in children] == ["Revenue", "Costs"]
    assert [child.values for child in children] == [(100.0,), (40.0,)]


def test_stmt_group_nests_statement_items_without_values():
    Revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        name="Revenue",
    )
    Costs = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 40.0)],
        name="Costs",
    )

    ctx = Context()
    rows = Stmt(Group([Revenue, Costs])).values(
        ctx,
        [Period(date(2025, 1, 1), date(2025, 2, 1))],
    )

    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, GroupRow)
    children = [child for child in row.children if isinstance(child, LineRow)]
    assert len(children) == 2
    assert [child.name for child in children] == ["Revenue", "Costs"]


def test_stmt_values_accepts_reducer_for_periods_with_multiple_spans():
    Revenue = span.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), 100.0),
            ((date(2025, 2, 1), date(2025, 3, 1)), 200.0),
        ],
        name="Revenue",
    )

    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 3, 1))

    with pytest.raises(ValueError, match="requires a reducer"):
        Stmt(Revenue).values(ctx, [period])

    rows = Stmt(Revenue).values(ctx, [period], reducer=sum_spans(0.0))

    row = rows[0]
    assert isinstance(row, LineRow)
    assert row.values == (300.0,)


def test_stmt_values_expands_family_rows_by_key_across_periods():
    q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
    q2 = Period(date(2025, 4, 1), date(2025, 7, 1))

    class RevenueByCustomer(SpanSeriesFamily[str]):
        label = "Revenue by Customer"

        def key_label(self, key: str) -> str:
            return key.title()

        def spans(self, period: Period) -> SpanFamilyResult[str]:
            if period == q1:
                return {
                    "alpha": (Span(period, Formula.pure(100.0), no_split),),
                    "beta": (Span(period, Formula.pure(40.0), no_split),),
                }
            if period == q2:
                return {
                    "beta": (Span(period, Formula.pure(50.0), no_split),),
                    "gamma": (Span(period, Formula.pure(10.0), no_split),),
                }
            return {}

    ctx = Context()
    rows = Stmt(RevenueByCustomer).values(ctx, [q1, q2])

    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row, FamilyRow)
    assert row.name == "Revenue by Customer"
    assert row.family is RevenueByCustomer
    assert all(isinstance(child, FamilyLineRow) for child in row.children)
    assert [child.name for child in row.children] == ["Alpha", "Beta", "Gamma"]
    assert [child.key for child in row.children] == ["alpha", "beta", "gamma"]
    assert [child.values for child in row.children] == [
        (100.0, None),
        (40.0, 50.0),
        (None, 10.0),
    ]


def test_stmt_values_reduces_family_spans_per_key_and_period():
    q1 = Period(date(2025, 1, 1), date(2025, 4, 1))

    class RevenueByCustomer(SpanSeriesFamily[str]):
        def spans(self, period: Period) -> SpanFamilyResult[str]:
            return {
                "alpha": (
                    Span(Period(date(2025, 1, 1), date(2025, 2, 1)), Formula.pure(100.0), no_split),
                    Span(Period(date(2025, 2, 1), date(2025, 4, 1)), Formula.pure(200.0), no_split),
                )
            }

    ctx = Context()

    with pytest.raises(ValueError, match="requires a reducer"):
        Stmt(RevenueByCustomer).values(ctx, [q1])

    rows = Stmt(RevenueByCustomer).values(ctx, [q1], reducer=sum_spans(0.0))

    row = rows[0]
    assert isinstance(row, FamilyRow)
    assert row.children[0].values == (300.0,)
