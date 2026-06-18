from datetime import date
from typing import Iterable

import pytest

from orcaset import (
    Context,
    DateValue,
    Formula,
    Group,
    GroupRow,
    LineRow,
    Period,
    PeriodValue,
    StatementResult,
    Stmt,
    Total,
    TotalRow,
    point,
    span,
    sum_spans,
)


def row_values(row: LineRow | TotalRow) -> tuple[float | None, ...]:
    return tuple(value.value for value in row.values)


def rows(result: StatementResult) -> tuple[GroupRow | LineRow | TotalRow, ...]:
    return result.rows


def test_stmt_values_uses_series_label_for_line_items():
    revenue = span.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), 100.0),
            ((date(2025, 2, 1), date(2025, 3, 1)), 200.0),
        ],
        agg=sum_spans(0.0),
        label="Revenue",
    )

    ctx = Context()
    result = Stmt(revenue).values(
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
    assert isinstance(result_rows[0], LineRow)
    assert result_rows[0].name == "Revenue"
    assert result_rows[0].series is revenue
    assert [value.period for value in result_rows[0].values if isinstance(value, PeriodValue)] == [
        Period(date(2025, 1, 1), date(2025, 2, 1)),
        Period(date(2025, 2, 1), date(2025, 3, 1)),
    ]
    assert row_values(result_rows[0]) == (100.0, 200.0)


def test_stmt_total_uses_real_series_and_nests_children():
    revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        label="Revenue",
    )
    costs = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), -40.0)],
        agg=sum_spans(0.0),
        label="Costs",
    )
    income = span.sum([revenue, costs], agg=sum_spans(0.0), label="Income")

    ctx = Context()
    result_rows = rows(
        Stmt(Total(income, [revenue, costs])).values(
            ctx,
            [Period(date(2025, 1, 1), date(2025, 2, 1))],
        )
    )

    assert len(result_rows) == 1
    row = result_rows[0]
    assert isinstance(row, TotalRow)
    assert row.name == "Income"
    assert row.series is income
    assert len(row.children) == 2
    assert [child.name for child in row.children if isinstance(child, LineRow)] == [
        "Revenue",
        "Costs",
    ]
    assert row_values(row) == (60.0,)


def test_stmt_group_wraps_rows_with_group_row():
    revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        label="Revenue",
    )
    costs = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), -40.0)],
        agg=sum_spans(0.0),
        label="Costs",
    )

    ctx = Context()
    result_rows = rows(
        Stmt(Group([revenue, costs])).values(
            ctx,
            [Period(date(2025, 1, 1), date(2025, 2, 1))],
        )
    )

    assert len(result_rows) == 1
    assert isinstance(result_rows[0], GroupRow)
    assert [row.name for row in result_rows[0].children if isinstance(row, LineRow)] == [
        "Revenue",
        "Costs",
    ]


def test_stmt_expands_keyed_span_series_for_period_queries():
    created: list[Period] = []
    seen_periods: list[Period] = []

    def keys(period: Period) -> Iterable[Period]:
        seen_periods.append(period)
        return [period]

    def series_for(period: Period):
        created.append(period)
        return span.from_list(
            [((period.start, period.end), 10.0)],
            agg=sum_spans(0.0),
            label=f"Cohort {period.start:%Y-%m-%d}",
        )

    cohorts = span.keyed(keys, series_for, label="Cohorts")
    periods = [
        Period(date(2025, 1, 1), date(2025, 2, 1)),
        Period(date(2025, 2, 1), date(2025, 3, 1)),
    ]

    ctx = Context()
    result_rows = rows(Stmt(cohorts).values(ctx, periods))

    assert seen_periods == periods
    assert created == periods
    assert cohorts.get(ctx, periods[0]) is cohorts.get(ctx, periods[0])

    other_ctx = Context()
    assert cohorts.get(ctx, periods[0]) is not cohorts.get(other_ctx, periods[0])
    assert created == periods + [periods[0]]

    assert len(result_rows) == 1
    assert isinstance(result_rows[0], GroupRow)
    assert [row.name for row in result_rows[0].children if isinstance(row, LineRow)] == [
        "Cohort 2025-01-01",
        "Cohort 2025-02-01",
    ]


def test_keyed_span_series_rejects_date_queries():
    def series_for(period: Period):
        return span.from_list(
            [((period.start, period.end), 10.0)],
            agg=sum_spans(0.0),
            label="Unused",
        )

    cohorts = span.keyed(lambda _period: (), series_for, label="Cohorts")

    with pytest.raises(TypeError, match="period queries"):
        Stmt(cohorts).values_for_dates(Context(), [date(2025, 1, 1)])


def test_stmt_expands_keyed_point_series_for_period_queries():
    created: list[int] = []
    seen_dates: list[date] = []

    def keys(dt: date) -> Iterable[int]:
        seen_dates.append(dt)
        return [1, 2]

    def series_for(key: int):
        created.append(key)

        @point.derived(label=f"Tranche {key}")
        def tranche(_: Context, dt: date) -> Formula[float | None]:
            return Formula.pure(float(key * 100 + dt.month))

        return tranche

    tranches = point.keyed(keys, series_for, label="Tranches")
    periods = [
        Period(date(2025, 1, 1), date(2025, 4, 1)),
        Period(date(2025, 4, 1), date(2025, 7, 1)),
    ]

    ctx = Context()
    result = Stmt(tranches).values(ctx, periods)
    result_rows = rows(result)

    assert seen_dates == [date(2025, 1, 1), date(2025, 4, 1), date(2025, 7, 1)]
    assert created == [1, 2]
    assert tranches.get(ctx, 1) is tranches.get(ctx, 1)

    other_ctx = Context()
    assert tranches.get(ctx, 1) is not tranches.get(other_ctx, 1)
    assert created == [1, 2, 1]

    assert len(result_rows) == 1
    assert isinstance(result_rows[0], GroupRow)
    child_rows = result_rows[0].children
    assert [row.name for row in child_rows if isinstance(row, LineRow)] == [
        "Tranche 1",
        "Tranche 2",
    ]
    assert [row_values(row) for row in child_rows if isinstance(row, LineRow)] == [
        (101.0, 104.0, 107.0),
        (201.0, 204.0, 207.0),
    ]


def test_stmt_expands_keyed_point_series_for_date_queries():
    seen_dates: list[date] = []

    def keys(dt: date) -> Iterable[str]:
        seen_dates.append(dt)
        return ["cash", "debt"]

    def series_for(key: str):
        @point.derived(label=key.title())
        def balance(_: Context, dt: date) -> Formula[float | None]:
            sign = 1.0 if key == "cash" else -1.0
            return Formula.pure(sign * dt.month)

        return balance

    balances = point.keyed(keys, series_for, label="Balances")
    dates = [date(2025, 1, 1), date(2025, 4, 1)]

    result_rows = rows(Stmt(balances).values_for_dates(Context(), dates))

    assert seen_dates == dates
    assert len(result_rows) == 1
    assert isinstance(result_rows[0], GroupRow)
    child_rows = result_rows[0].children
    assert [row.name for row in child_rows if isinstance(row, LineRow)] == ["Cash", "Debt"]
    assert [row_values(row) for row in child_rows if isinstance(row, LineRow)] == [
        (1.0, 4.0),
        (-1.0, -4.0),
    ]


def test_stmt_period_query_evaluates_point_series_at_period_boundaries():
    cash = span.from_list([], agg=sum_spans(0.0), label="Cash Flow")

    balance = point.from_list(
        [
            (date(2025, 1, 1), 10.0),
            (date(2025, 4, 1), 20.0),
            (date(2025, 7, 1), 30.0),
        ],
        label="Balance",
    )

    ctx = Context()
    result = Stmt(cash, balance).values_for_periods(
        ctx,
        [Period(date(2025, 1, 1), date(2025, 4, 1)), Period(date(2025, 4, 1), date(2025, 7, 1))],
    )
    result_rows = rows(result)

    assert result.dates == (date(2025, 1, 1), date(2025, 4, 1), date(2025, 7, 1))
    assert isinstance(result_rows[0], LineRow)
    assert isinstance(result_rows[1], LineRow)
    assert all(isinstance(value, PeriodValue) for value in result_rows[0].values)
    assert all(isinstance(value, DateValue) for value in result_rows[1].values)
    assert row_values(result_rows[0]) == (0.0, 0.0)
    assert row_values(result_rows[1]) == (10.0, 20.0, 30.0)


def test_stmt_date_query_evaluates_points_and_returns_na_for_spans():
    revenue = span.from_list([], agg=sum_spans(0.0), label="Revenue")

    balance = point.from_list(
        [
            (date(2025, 1, 1), 100.0),
            (date(2025, 4, 1), 120.0),
        ],
        label="Balance",
    )

    ctx = Context()
    result = Stmt(revenue, balance).values_for_dates(
        ctx,
        [date(2025, 1, 1), date(2025, 4, 1)],
    )
    result_rows = rows(result)

    assert result.periods == ()
    assert result.dates == (date(2025, 1, 1), date(2025, 4, 1))
    assert isinstance(result_rows[0], LineRow)
    assert isinstance(result_rows[1], LineRow)
    assert row_values(result_rows[0]) == (None, None)
    assert row_values(result_rows[1]) == (100.0, 120.0)
