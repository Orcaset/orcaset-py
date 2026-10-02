from datetime import date
from typing import Any

import pytest

import orcaset
from orcaset import (
    Context,
    Period,
    Series,
    YF,
    ops,
    period_union,
    stmt,
)
from orcaset.maybe import Na
from orcaset.query import accrue, exact


def row_values(row: stmt.LineRow | stmt.TotalRow) -> tuple[object, ...]:
    return tuple(value.value for value in row.values)


def cells(row: stmt.LineRow | stmt.TotalRow) -> tuple[tuple[object, object, object], ...]:
    return tuple((value.key, value.query, value.value) for value in row.values)


def rows(result: stmt.StatementResult) -> tuple[stmt.GroupRow | stmt.LineRow | stmt.TotalRow, ...]:
    return result.rows


def test_stmt_types_are_exported_only_from_stmt_module():
    names = {
        "Group",
        "GroupRow",
        "LineRow",
        "StatementResult",
        "Stmt",
        "StmtItem",
        "StmtKey",
        "StmtRow",
        "StmtSeries",
        "StmtValue",
        "Total",
        "TotalRow",
    }

    assert set(orcaset.stmt.__all__) == names
    assert all(not hasattr(orcaset, name) for name in names)


def test_stmt_values_uses_series_name_for_line_items():
    revenue = Series.of(
        "Revenue",
        exact,
        [
            (Period(date(2025, 1, 1), date(2025, 2, 1)), 100.0),
            (Period(date(2025, 2, 1), date(2025, 3, 1)), 200.0),
        ],
    )

    ctx = Context()
    result = stmt.Stmt(revenue).values(
        ctx,
        [
            Period(date(2025, 1, 1), date(2025, 2, 1)),
            Period(date(2025, 2, 1), date(2025, 3, 1)),
        ],
    )
    result_rows = rows(result)

    assert result.periods == (
        Period(date(2025, 1, 1), date(2025, 2, 1)),
        Period(date(2025, 2, 1), date(2025, 3, 1)),
    )
    assert result.dates == ()
    assert len(result_rows) == 1
    assert isinstance(result_rows[0], stmt.LineRow)
    assert result_rows[0].name == "Revenue"
    assert result_rows[0].series is revenue
    assert [value.key for value in result_rows[0].values] == [
        Period(date(2025, 1, 1), date(2025, 2, 1)),
        Period(date(2025, 2, 1), date(2025, 3, 1)),
    ]
    assert row_values(result_rows[0]) == (100.0, 200.0)


def test_stmt_total_uses_real_series_and_nests_children():
    revenue = Series.of(
        "Revenue",
        exact,
        [(Period(date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
    )
    costs = Series.of(
        "Costs",
        exact,
        [(Period(date(2025, 1, 1), date(2025, 2, 1)), -40.0)],
    )
    income = ops.add("Income", revenue, costs, merge_keys=period_union)

    ctx = Context()
    result_rows = rows(
        stmt.Stmt(stmt.Total(income, [revenue, costs])).values(
            ctx,
            [Period(date(2025, 1, 1), date(2025, 2, 1))],
        )
    )

    assert len(result_rows) == 1
    row = result_rows[0]
    assert isinstance(row, stmt.TotalRow)
    assert row.name == "Income"
    assert row.series is income
    assert len(row.children) == 2
    assert [child.name for child in row.children if isinstance(child, stmt.LineRow)] == [
        "Revenue",
        "Costs",
    ]
    assert row_values(row) == (60.0,)


def test_stmt_group_wraps_rows_with_group_row():
    revenue = Series.of(
        "Revenue",
        exact,
        [(Period(date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
    )
    costs = Series.of(
        "Costs",
        exact,
        [(Period(date(2025, 1, 1), date(2025, 2, 1)), -40.0)],
    )

    ctx = Context()
    result_rows = rows(
        stmt.Stmt(stmt.Group(revenue, costs)).values(
            ctx,
            [Period(date(2025, 1, 1), date(2025, 2, 1))],
        )
    )

    assert len(result_rows) == 1
    assert isinstance(result_rows[0], stmt.GroupRow)
    assert result_rows[0].label is None
    assert [row.name for row in result_rows[0].children if isinstance(row, stmt.LineRow)] == [
        "Revenue",
        "Costs",
    ]


def test_stmt_group_optional_label_is_copied_to_group_row():
    revenue = Series.of(
        "Revenue",
        exact,
        [(Period(date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
    )
    costs = Series.of(
        "Costs",
        exact,
        [(Period(date(2025, 1, 1), date(2025, 2, 1)), -40.0)],
    )

    ctx = Context()
    result_rows = rows(
        stmt.Stmt(stmt.Group(revenue, costs, label="Income")).values(
            ctx,
            [Period(date(2025, 1, 1), date(2025, 2, 1))],
        )
    )

    assert len(result_rows) == 1
    assert isinstance(result_rows[0], stmt.GroupRow)
    assert result_rows[0].label == "Income"
    assert [row.name for row in result_rows[0].children if isinstance(row, stmt.LineRow)] == [
        "Revenue",
        "Costs",
    ]


def test_stmt_group_optional_label_is_copied_on_date_query():
    balance = Series.of(
        "Balance",
        exact,
        [(date(2025, 1, 1), 100.0)],
    )

    ctx = Context()
    result_rows = rows(
        stmt.Stmt(stmt.Group(balance, label="Assets")).values(
            ctx,
            [date(2025, 1, 1)],
        )
    )

    assert len(result_rows) == 1
    assert isinstance(result_rows[0], stmt.GroupRow)
    assert result_rows[0].label == "Assets"


def test_stmt_period_query_evaluates_date_series_at_period_ends():
    cash = Series.of("Cash Flow", exact, [])
    balance = Series.of(
        "Balance",
        exact,
        [
            (date(2025, 1, 1), 10.0),
            (date(2025, 4, 1), 20.0),
            (date(2025, 7, 1), 30.0),
        ],
    )
    q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
    q2 = Period(date(2025, 4, 1), date(2025, 7, 1))

    ctx = Context()
    result = stmt.Stmt(cash, balance).values(ctx, [q1, q2])
    result_rows = rows(result)

    assert result.periods == (q1, q2)
    assert result.dates == ()
    assert isinstance(result_rows[0], stmt.LineRow)
    assert isinstance(result_rows[1], stmt.LineRow)
    assert row_values(result_rows[0]) == (Na, Na)
    assert cells(result_rows[1]) == ((q1, q1.end, 20.0), (q2, q2.end, 30.0))
    assert all(value.series is balance for value in result_rows[1].values)


def test_stmt_period_query_keeps_input_order_gaps_overlap_and_nesting():
    q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
    q2 = Period(date(2025, 4, 1), date(2025, 7, 1))
    q4 = Period(date(2025, 10, 1), date(2026, 1, 1))
    h1 = Period(date(2025, 1, 1), date(2025, 7, 1))
    revenue = Series.of("Revenue", accrue(YF.act360), [(q1, 1.0), (q2, 2.0), (q4, 4.0)])
    balance = Series.of(
        "Balance",
        exact,
        [
            (date(2025, 4, 1), 20.0),
            (date(2025, 7, 1), 30.0),
            (date(2026, 1, 1), 50.0),
        ],
    )
    periods = [q4, q2, q1, h1]

    ctx = Context()
    result = stmt.Stmt(revenue, balance).values(ctx, periods)
    revenue_row, balance_row = rows(result)

    assert result.periods == tuple(periods)
    assert isinstance(revenue_row, stmt.LineRow)
    assert isinstance(balance_row, stmt.LineRow)
    assert [value.key for value in revenue_row.values] == periods
    assert row_values(revenue_row) == (4.0, 2.0, 1.0, 3.0)
    # q2 and h1 share an end, so both get the closing balance.
    assert cells(balance_row) == (
        (q4, q4.end, 50.0),
        (q2, q2.end, 30.0),
        (q1, q1.end, 20.0),
        (h1, h1.end, 30.0),
    )


def test_stmt_values_accepts_dates():
    revenue = Series.of("Revenue", exact, [(Period(date(2025, 1, 1), date(2025, 4, 1)), 5.0)])
    balance = Series.of(
        "Balance",
        exact,
        [
            (date(2025, 1, 1), 100.0),
            (date(2025, 4, 1), 120.0),
        ],
    )

    ctx = Context()
    result = stmt.Stmt(revenue, balance).values(ctx, [date(2025, 4, 1), date(2025, 1, 1)])
    revenue_row, balance_row = rows(result)

    assert result.periods == ()
    assert result.dates == (date(2025, 4, 1), date(2025, 1, 1))
    assert isinstance(revenue_row, stmt.LineRow)
    assert isinstance(balance_row, stmt.LineRow)
    assert cells(revenue_row) == (
        (date(2025, 4, 1), None, Na),
        (date(2025, 1, 1), None, Na),
    )
    assert cells(balance_row) == (
        (date(2025, 4, 1), date(2025, 4, 1), 120.0),
        (date(2025, 1, 1), date(2025, 1, 1), 100.0),
    )


def test_stmt_values_accepts_mixed_periods_and_dates_in_input_order():
    q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
    q2 = Period(date(2025, 4, 1), date(2025, 7, 1))
    revenue = Series.of("Revenue", exact, [(q1, 5.0), (q2, 6.0)])
    balance = Series.of(
        "Balance",
        exact,
        [
            (date(2025, 1, 1), 100.0),
            (date(2025, 4, 1), 120.0),
            (date(2025, 7, 1), 130.0),
        ],
    )
    opening = date(2025, 1, 1)

    ctx = Context()
    result = stmt.Stmt(revenue, balance).values(ctx, [opening, q1, q2])
    revenue_row, balance_row = rows(result)

    assert result.keys == (opening, q1, q2)
    assert result.periods == (q1, q2)
    assert result.dates == (opening,)
    assert isinstance(revenue_row, stmt.LineRow)
    assert isinstance(balance_row, stmt.LineRow)
    assert cells(revenue_row) == (
        (opening, None, Na),
        (q1, q1, 5.0),
        (q2, q2, 6.0),
    )
    assert cells(balance_row) == (
        (opening, opening, 100.0),
        (q1, q1.end, 120.0),
        (q2, q2.end, 130.0),
    )


def test_stmt_date_query_evaluates_dates_and_returns_none_for_period_series():
    revenue = Series.of("Revenue", exact, [])
    balance = Series.of(
        "Balance",
        exact,
        [
            (date(2025, 1, 1), 100.0),
            (date(2025, 4, 1), 120.0),
        ],
    )

    ctx = Context()
    result = stmt.Stmt(revenue, balance).values(
        ctx,
        [date(2025, 1, 1), date(2025, 4, 1)],
    )
    result_rows = rows(result)

    assert result.periods == ()
    assert result.dates == (date(2025, 1, 1), date(2025, 4, 1))
    assert isinstance(result_rows[0], stmt.LineRow)
    assert isinstance(result_rows[1], stmt.LineRow)
    assert row_values(result_rows[0]) == (Na, Na)
    assert row_values(result_rows[1]) == (100.0, 120.0)


def test_stmt_converts_na_answers_to_none():
    revenue = Series.of(
        "Revenue",
        exact,
        [(Period(date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
    )

    ctx = Context()
    result_rows = rows(
        stmt.Stmt(revenue).values(
            ctx,
            [
                Period(date(2025, 1, 1), date(2025, 2, 1)),
                Period(date(2025, 2, 1), date(2025, 3, 1)),
            ],
        )
    )

    assert isinstance(result_rows[0], stmt.LineRow)
    assert row_values(result_rows[0]) == (100.0, Na)


def test_stmt_rejects_items_that_are_not_series_totals_or_groups():
    bad: Any = "Revenue"

    with pytest.raises(TypeError, match="Series, Total, or Group"):
        stmt.Stmt(bad).values(Context(), [Period(date(2025, 1, 1), date(2025, 4, 1))])


def test_stmt_value_keeps_model_value_unchanged():
    class Cited(float):
        source: str

    cited = Cited(100.0)
    cited.source = "10-K"
    q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
    revenue = Series.of("Revenue", exact, [(q1, cited)])

    (row,) = rows(stmt.Stmt(revenue).values(Context(), [q1]))

    assert isinstance(row, stmt.LineRow)
    (value,) = row.values
    assert value.value is cited
