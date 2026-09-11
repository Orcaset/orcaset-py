from datetime import date

import orcaset
from orcaset import (
    Context,
    Period,
    Series,
    ops,
    period_union,
    stmt,
)
from orcaset.query import exact


def row_values(row: stmt.LineRow | stmt.TotalRow) -> tuple[float | None, ...]:
    return tuple(value.value for value in row.values)


def rows(result: stmt.StatementResult) -> tuple[stmt.GroupRow | stmt.LineRow | stmt.TotalRow, ...]:
    return result.rows


def test_stmt_types_are_exported_only_from_stmt_module():
    names = {
        "DateValue",
        "Group",
        "GroupRow",
        "LineRow",
        "PeriodValue",
        "StatementResult",
        "Stmt",
        "StmtItem",
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
    assert result.dates == (date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1))
    assert len(result_rows) == 1
    assert isinstance(result_rows[0], stmt.LineRow)
    assert result_rows[0].name == "Revenue"
    assert result_rows[0].series is revenue
    assert [value.period for value in result_rows[0].values if isinstance(value, stmt.PeriodValue)] == [
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
    assert [row.name for row in result_rows[0].children if isinstance(row, stmt.LineRow)] == [
        "Revenue",
        "Costs",
    ]


def test_stmt_period_query_evaluates_date_series_at_period_boundaries():
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

    ctx = Context()
    result = stmt.Stmt(cash, balance).values_for_periods(
        ctx,
        [Period(date(2025, 1, 1), date(2025, 4, 1)), Period(date(2025, 4, 1), date(2025, 7, 1))],
    )
    result_rows = rows(result)

    assert result.dates == (date(2025, 1, 1), date(2025, 4, 1), date(2025, 7, 1))
    assert isinstance(result_rows[0], stmt.LineRow)
    assert isinstance(result_rows[1], stmt.LineRow)
    assert all(isinstance(value, stmt.PeriodValue) for value in result_rows[0].values)
    assert all(isinstance(value, stmt.DateValue) for value in result_rows[1].values)
    assert row_values(result_rows[0]) == (None, None)
    assert row_values(result_rows[1]) == (10.0, 20.0, 30.0)


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
    result = stmt.Stmt(revenue, balance).values_for_dates(
        ctx,
        [date(2025, 1, 1), date(2025, 4, 1)],
    )
    result_rows = rows(result)

    assert result.periods == ()
    assert result.dates == (date(2025, 1, 1), date(2025, 4, 1))
    assert isinstance(result_rows[0], stmt.LineRow)
    assert isinstance(result_rows[1], stmt.LineRow)
    assert row_values(result_rows[0]) == (None, None)
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
    assert row_values(result_rows[0]) == (100.0, None)
