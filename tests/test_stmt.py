from datetime import date
from typing import Iterable, Sequence

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


def rows(result: StatementResult) -> tuple:
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
    seen_periods: list[tuple[Period, ...]] = []

    def keys(_: Context, periods: Sequence[Period]) -> Iterable[Period]:
        seen_periods.append(tuple(periods))
        return periods

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

    assert seen_periods == [tuple(periods)]
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

    cohorts = span.keyed(lambda _ctx, _periods: (), series_for, label="Cohorts")

    with pytest.raises(TypeError, match="period queries"):
        Stmt(cohorts).values_for_dates(Context(), [date(2025, 1, 1)])


def test_stmt_period_query_evaluates_point_series_at_period_boundaries():
    cash = span.from_list([], agg=sum_spans(0.0), label="Cash Flow")

    @point.define(label="Balance")
    def balance(ctx: Context, dt: date) -> Formula[float | None]:
        values = {
            date(2025, 1, 1): 10.0,
            date(2025, 4, 1): 20.0,
            date(2025, 7, 1): 30.0,
        }
        return Formula.pure(values[dt])

    ctx = Context()
    result = Stmt(cash, balance).values_for_periods(
        ctx,
        [Period(date(2025, 1, 1), date(2025, 4, 1)), Period(date(2025, 4, 1), date(2025, 7, 1))],
    )
    result_rows = rows(result)

    assert result.dates == (date(2025, 1, 1), date(2025, 4, 1), date(2025, 7, 1))
    assert all(isinstance(value, PeriodValue) for value in result_rows[0].values)
    assert all(isinstance(value, DateValue) for value in result_rows[1].values)
    assert row_values(result_rows[0]) == (0.0, 0.0)
    assert row_values(result_rows[1]) == (10.0, 20.0, 30.0)


def test_stmt_date_query_evaluates_points_and_returns_na_for_spans():
    revenue = span.from_list([], agg=sum_spans(0.0), label="Revenue")

    @point.define(label="Balance")
    def balance(ctx: Context, dt: date) -> Formula[float | None]:
        return Formula.pure(100.0 if dt == date(2025, 1, 1) else 120.0)

    ctx = Context()
    result = Stmt(revenue, balance).values_for_dates(
        ctx,
        [date(2025, 1, 1), date(2025, 4, 1)],
    )
    result_rows = rows(result)

    assert result.periods == ()
    assert result.dates == (date(2025, 1, 1), date(2025, 4, 1))
    assert row_values(result_rows[0]) == (None, None)
    assert row_values(result_rows[1]) == (100.0, 120.0)
