from datetime import date

from orcaset import (
    Context,
    DateValue,
    FamilyLineRow,
    FamilyRow,
    Formula,
    Group,
    GroupRow,
    LineRow,
    Period,
    PeriodValue,
    Point,
    PointFamilyResult,
    PointSeries,
    PointSeriesFamily,
    Span,
    SpanFamilyResult,
    SpanSeries,
    SpanSeriesFamily,
    StatementResult,
    Stmt,
    Total,
    TotalRow,
    span,
    sum_spans,
)


def row_values(row: LineRow | TotalRow | FamilyLineRow) -> tuple[float | None, ...]:
    return tuple(value.value for value in row.values)


def rows(result: StatementResult) -> tuple:
    return result.rows


class _TestSpanSeries(SpanSeries):
    @staticmethod
    def agg(spans: list[Span]) -> float | None:
        return sum_spans(0.0)(spans)

    def spans(self):
        raise NotImplementedError


def test_stmt_values_uses_series_class_name_for_line_items():
    Revenue = span.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), 100.0),
            ((date(2025, 2, 1), date(2025, 3, 1)), 200.0),
        ],
        agg=sum_spans(0.0),
        name="Revenue",
    )

    ctx = Context()
    result = Stmt(Revenue).values(
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
    assert result_rows[0].series is Revenue
    assert [value.period for value in result_rows[0].values if isinstance(value, PeriodValue)] == [
        Period(date(2025, 1, 1), date(2025, 2, 1)),
        Period(date(2025, 2, 1), date(2025, 3, 1)),
    ]
    assert row_values(result_rows[0]) == (100.0, 200.0)


def test_stmt_values_prefers_series_label_for_line_items():
    Revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        name="Revenue",
    )
    Revenue.label = "Net Revenue"

    ctx = Context()
    result_rows = rows(
        Stmt(Revenue).values(
            ctx,
            [Period(date(2025, 1, 1), date(2025, 2, 1))],
        )
    )

    assert len(result_rows) == 1
    assert isinstance(result_rows[0], LineRow)
    assert result_rows[0].name == "Net Revenue"


def test_stmt_total_uses_real_series_and_nests_children():
    Revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        name="Revenue",
    )
    Costs = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 40.0)],
        agg=sum_spans(0.0),
        name="Costs",
    )
    Income = span.sub(Revenue, Costs, agg=sum_spans(0.0))

    ctx = Context()
    result_rows = rows(
        Stmt(Total(Income, [Revenue, Costs])).values(
            ctx,
            [Period(date(2025, 1, 1), date(2025, 2, 1))],
        )
    )

    assert len(result_rows) == 1
    row = result_rows[0]
    assert isinstance(row, TotalRow)
    assert row.name == "SubRevenueCosts"
    assert row.series is Income
    assert row_values(row) == (60.0,)
    children = [child for child in row.children if isinstance(child, LineRow)]
    assert len(children) == 2
    assert [child.name for child in children] == ["Revenue", "Costs"]
    assert [row_values(child) for child in children] == [(100.0,), (40.0,)]


def test_stmt_group_nests_statement_items_without_values():
    Revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        name="Revenue",
    )
    Costs = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 40.0)],
        agg=sum_spans(0.0),
        name="Costs",
    )

    ctx = Context()
    result_rows = rows(
        Stmt(Group([Revenue, Costs])).values(
            ctx,
            [Period(date(2025, 1, 1), date(2025, 2, 1))],
        )
    )

    assert len(result_rows) == 1
    row = result_rows[0]
    assert isinstance(row, GroupRow)
    children = [child for child in row.children if isinstance(child, LineRow)]
    assert len(children) == 2
    assert [child.name for child in children] == ["Revenue", "Costs"]


def test_stmt_values_uses_series_agg_for_periods_with_multiple_spans():
    Revenue = span.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), 100.0),
            ((date(2025, 2, 1), date(2025, 3, 1)), 200.0),
        ],
        agg=sum_spans(0.0),
        name="Revenue",
    )

    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 3, 1))

    result_rows = rows(Stmt(Revenue).values(ctx, [period]))

    row = result_rows[0]
    assert isinstance(row, LineRow)
    assert row_values(row) == (300.0,)


def test_stmt_values_expands_family_rows_by_key_across_periods():
    q1 = Period(date(2025, 1, 1), date(2025, 4, 1))
    q2 = Period(date(2025, 4, 1), date(2025, 7, 1))
    data = {
        "alpha": {q1: 100.0},
        "beta": {q1: 40.0, q2: 50.0},
        "gamma": {q2: 10.0},
    }

    def customer_series(key: str) -> type[SpanSeries]:
        return span.from_list(
            [((period.start, period.end), value) for period, value in data[key].items()],
            agg=sum_spans(0.0),
            name=f"{key.title()}Revenue",
        )

    class RevenueByCustomer(SpanSeriesFamily[str]):
        label = "Revenue by Customer"

        def key_label(self, key: str) -> str:
            return key.title()

        def spans(self, period: Period) -> SpanFamilyResult[str]:
            result: dict[str, tuple[Span, ...]] = {}
            for key, values in data.items():
                if period not in values:
                    continue
                customer = self.ctx.get_or_create_family_series(
                    self,
                    key,
                    lambda key=key: customer_series(key),
                )
                result[key] = tuple(customer.query(period).eval())
            return result

    ctx = Context()
    result_rows = rows(Stmt(RevenueByCustomer).values(ctx, [q1, q2]))

    assert len(result_rows) == 1
    row = result_rows[0]
    assert isinstance(row, FamilyRow)
    assert row.name == "Revenue by Customer"
    assert row.family is RevenueByCustomer
    assert all(isinstance(child, FamilyLineRow) for child in row.children)
    assert [child.name for child in row.children] == ["Alpha", "Beta", "Gamma"]
    assert [child.key for child in row.children] == ["alpha", "beta", "gamma"]
    assert [row_values(child) for child in row.children] == [
        (100.0, None),
        (40.0, 50.0),
        (None, 10.0),
    ]


def test_stmt_values_reduces_family_spans_per_key_and_period():
    q1 = Period(date(2025, 1, 1), date(2025, 4, 1))

    def customer_series() -> type[SpanSeries]:
        return span.from_list(
            [
                ((date(2025, 1, 1), date(2025, 2, 1)), 100.0),
                ((date(2025, 2, 1), date(2025, 4, 1)), 200.0),
            ],
            agg=sum_spans(0.0),
            name="AlphaRevenue",
        )

    class RevenueByCustomer(SpanSeriesFamily[str]):
        def spans(self, period: Period) -> SpanFamilyResult[str]:
            alpha = self.ctx.get_or_create_family_series(self, "alpha", customer_series)
            return {
                "alpha": tuple(alpha.query(period).eval()),
            }

    ctx = Context()

    result_rows = rows(Stmt(RevenueByCustomer).values(ctx, [q1]))

    row = result_rows[0]
    assert isinstance(row, FamilyRow)
    assert row_values(row.children[0]) == (300.0,)


def test_stmt_period_query_evaluates_point_series_at_period_boundaries():
    p1 = Period(date(2025, 1, 1), date(2025, 4, 1))
    p2 = Period(date(2025, 4, 1), date(2025, 7, 1))

    class Cash(_TestSpanSeries):
        def spans(self):
            return ()

    class Balance(PointSeries):
        def point(self, dt: date) -> Formula[float | None]:
            values = {
                date(2025, 1, 1): 10.0,
                date(2025, 4, 1): 20.0,
                date(2025, 7, 1): 30.0,
            }
            return Formula.pure(values[dt])

    ctx = Context()
    result = Stmt(Cash, Balance).values_for_periods(ctx, [p1, p2])
    result_rows = rows(result)

    assert result.dates == (date(2025, 1, 1), date(2025, 4, 1), date(2025, 7, 1))
    assert isinstance(result_rows[0], LineRow)
    assert isinstance(result_rows[1], LineRow)
    assert all(isinstance(value, PeriodValue) for value in result_rows[0].values)
    assert all(isinstance(value, DateValue) for value in result_rows[1].values)
    assert row_values(result_rows[0]) == (0.0, 0.0)
    assert row_values(result_rows[1]) == (10.0, 20.0, 30.0)


def test_stmt_date_query_evaluates_points_and_returns_na_for_spans():
    class Revenue(_TestSpanSeries):
        def spans(self):
            return ()

    class Balance(PointSeries):
        def point(self, dt: date) -> Formula[float | None]:
            return Formula.pure(100.0 if dt == date(2025, 1, 1) else 120.0)

    ctx = Context()
    result = Stmt(Revenue, Balance).values_for_dates(
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


def test_stmt_period_query_expands_point_family_rows_by_key_across_boundaries():
    p1 = Period(date(2025, 1, 1), date(2025, 4, 1))
    p2 = Period(date(2025, 4, 1), date(2025, 7, 1))

    class BalanceByAccount(PointSeriesFamily[str]):
        label = "Balance by Account"

        def key_label(self, key: str) -> str:
            return key.upper()

        def points(self, dt: date) -> PointFamilyResult[str]:
            if dt == date(2025, 1, 1):
                return {"cash": Point(dt, Formula.pure(10.0))}
            if dt == date(2025, 4, 1):
                return {
                    "cash": Point(dt, Formula.pure(20.0)),
                    "debt": Point(dt, Formula.pure(5.0)),
                }
            return {"debt": Point(dt, Formula.pure(7.0))}

    ctx = Context()
    result_rows = rows(Stmt(BalanceByAccount).values_for_periods(ctx, [p1, p2]))

    row = result_rows[0]
    assert isinstance(row, FamilyRow)
    assert row.name == "Balance by Account"
    assert [child.name for child in row.children] == ["CASH", "DEBT"]
    assert [row_values(child) for child in row.children] == [
        (10.0, 20.0, None),
        (None, 5.0, 7.0),
    ]


def test_stmt_date_query_returns_empty_span_family_row():
    class RevenueByCustomer(SpanSeriesFamily[str]):
        def spans(self, period: Period) -> SpanFamilyResult[str]:
            raise AssertionError("date queries should not evaluate span families")

    ctx = Context()
    result_rows = rows(Stmt(RevenueByCustomer).values_for_dates(ctx, [date(2025, 1, 1)]))

    row = result_rows[0]
    assert isinstance(row, FamilyRow)
    assert row.family is RevenueByCustomer
    assert row.children == ()
