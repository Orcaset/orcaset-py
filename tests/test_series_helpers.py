from datetime import date

import pytest
from dateutil.relativedelta import relativedelta

from orcaset import Context, Formula, Period, point, span, split_daily, sum_spans


def test_span_constant_and_periodic_constructors_create_series_defs():
    units = span.constant(
        10.0,
        agg=sum_spans(0.0),
        split=split_daily,
        start=date(2025, 1, 1),
        end=date(2025, 2, 1),
        label="Units",
    )
    rent = span.periodic(
        date(2025, 1, 1),
        relativedelta(months=1),
        100.0,
        agg=sum_spans(0.0),
        split=split_daily,
        end=date(2025, 4, 1),
        label="Rent",
    )

    ctx = Context()

    assert units.label == "Units"
    assert units.value(ctx, Period(date(2025, 1, 1), date(2025, 2, 1))).eval() == 10.0
    assert rent.value(ctx, Period(date(2025, 1, 1), date(2025, 4, 1))).eval() == 300.0


def test_point_operators_evaluate_dependencies():
    @point.define(label="A")
    def a(ctx: Context, dt: date) -> Formula[float | None]:
        return Formula.pure(10.0)

    @point.define(label="B")
    def b(ctx: Context, dt: date) -> Formula[float | None]:
        return Formula.pure(2.0)

    ctx = Context()
    dt = date(2025, 1, 1)

    assert point.neg(a).value(ctx, dt).eval() == -10.0
    assert point.sum([a, b]).value(ctx, dt).eval() == 12.0
    assert point.add_scalar(a, 2).value(ctx, dt).eval() == 12.0
    assert point.sub(a, b).value(ctx, dt).eval() == 8.0
    assert point.sub_scalar(a, 2).value(ctx, dt).eval() == 8.0
    assert point.rsub_scalar(12, a).value(ctx, dt).eval() == 2.0
    assert point.mul([a, b]).value(ctx, dt).eval() == 20.0
    assert point.div(a, b).value(ctx, dt).eval() == 5.0
    assert point.rdiv_scalar(20, a).value(ctx, dt).eval() == 2.0
    assert point.sum([a, b], label="Total").value(ctx, dt).eval() == 12.0


def test_point_accumulate_sums_span_changes():
    changes = span.from_list(
        [
            ((date(2025, 1, 1), date(2025, 1, 11)), 100.0),
            ((date(2025, 1, 11), date(2025, 2, 1)), None),
            ((date(2025, 2, 1), date(2025, 3, 1)), 200.0),
        ],
        agg=sum_spans(0.0),
        label="Changes",
    )
    balance = point.accumulate(date(2025, 1, 1), 1000.0, changes, label="Balance")

    ctx = Context()

    assert balance.value(ctx, date(2024, 12, 31)).eval() is None
    assert balance.value(ctx, date(2025, 1, 1)).eval() == 1000.0
    assert balance.value(ctx, date(2025, 1, 11)).eval() == pytest.approx(1100.0)
    assert balance.value(ctx, date(2025, 3, 1)).eval() == pytest.approx(1300.0)


def test_point_accumulate_accepts_lazy_span_series_ref():
    calls = 0
    changes = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        label="Changes",
    )

    def changes_ref() -> span.SpanSeriesDef:
        nonlocal calls
        calls += 1
        return changes

    balance = point.accumulate(date(2025, 1, 1), 1000.0, changes_ref, label="Balance")

    assert calls == 0

    ctx = Context()
    assert balance.value(ctx, date(2025, 2, 1)).eval() == pytest.approx(1100.0)
    assert balance.value(ctx, date(2025, 2, 1)).eval() == pytest.approx(1100.0)
    assert calls == 1


def test_point_operator_accepts_lazy_point_series_ref_with_fallback_label():
    calls = 0

    @point.define(label="A")
    def a(ctx: Context, dt: date) -> Formula[float | None]:
        return Formula.pure(10.0)

    def a_ref() -> point.PointSeriesDef:
        nonlocal calls
        calls += 1
        return a

    scaled = point.scale(a_ref, 2)

    assert scaled.label == "ScalePointSeries"
    assert calls == 0

    ctx = Context()
    assert scaled.value(ctx, date(2025, 1, 1)).eval() == 20.0
    assert calls == 1


def test_sequence_operators_accept_lazy_series_refs():
    @point.define(label="A")
    def a(ctx: Context, dt: date) -> Formula[float | None]:
        return Formula.pure(10.0)

    @point.define(label="B")
    def b(ctx: Context, dt: date) -> Formula[float | None]:
        return Formula.pure(2.0)

    left = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        label="Left",
    )
    right = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 50.0)],
        agg=sum_spans(0.0),
        label="Right",
    )

    ctx = Context()
    dt = date(2025, 1, 1)
    period = Period(date(2025, 1, 1), date(2025, 2, 1))

    assert point.sum([a, lambda: b]).value(ctx, dt).eval() == 12.0
    assert span.sum([left, lambda: right], agg=sum_spans(0.0)).value(ctx, period).eval() == 150.0


def test_span_operator_accepts_lazy_span_series_ref_and_inherits_agg():
    calls = 0
    revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        split=split_daily,
        label="Revenue",
    )

    def revenue_ref() -> span.SpanSeriesDef:
        nonlocal calls
        calls += 1
        return revenue

    doubled = span.scale(revenue_ref, 2)

    assert doubled.label == "ScaleSpanSeries"
    assert calls == 0

    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 2, 1))
    assert doubled.value(ctx, period).eval() == pytest.approx(200.0)
    assert doubled.value(ctx, period).eval() == pytest.approx(200.0)
    assert calls == 1


def test_span_clip_constructor_clips_base_series_window():
    revenue = span.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), 310.0),
            ((date(2025, 2, 1), date(2025, 3, 1)), 280.0),
        ],
        agg=sum_spans(0.0),
        split=split_daily,
        label="Revenue",
    )
    clipped = span.clip(
        revenue,
        start=date(2025, 1, 11),
        end=date(2025, 2, 11),
        label="ClippedRevenue",
    )

    ctx = Context()
    spans = clipped.query(ctx, Period(date(2025, 1, 1), date(2025, 3, 1))).eval()

    assert clipped.label == "ClippedRevenue"
    assert [span_cell.period for span_cell in spans] == [
        Period(date(2025, 1, 1), date(2025, 1, 11)),
        Period(date(2025, 1, 11), date(2025, 2, 1)),
        Period(date(2025, 2, 1), date(2025, 2, 11)),
        Period(date(2025, 2, 11), date(2025, 3, 1)),
    ]
    values = [span_cell.eval(ctx) for span_cell in spans]
    assert values[0] is None
    assert values[1:3] == pytest.approx([210.0, 100.0])
    assert values[3] is None
    assert clipped.value(ctx, Period(date(2025, 1, 1), date(2025, 3, 1))).eval() == (
        pytest.approx(310.0)
    )


def test_span_clip_accepts_lazy_span_series_ref():
    calls = 0
    revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 310.0)],
        agg=sum_spans(0.0),
        split=split_daily,
        label="Revenue",
    )

    def revenue_ref() -> span.SpanSeriesDef:
        nonlocal calls
        calls += 1
        return revenue

    clipped = span.clip(
        revenue_ref,
        start=date(2025, 1, 11),
        end=date(2025, 1, 21),
    )

    assert clipped.label == "ClipSpanSeries"
    assert calls == 0

    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 2, 1))
    assert clipped.value(ctx, period).eval() == pytest.approx(100.0)
    assert clipped.value(ctx, period).eval() == pytest.approx(100.0)
    assert calls == 1


def test_span_clip_rejects_invalid_window():
    revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 310.0)],
        agg=sum_spans(0.0),
        label="Revenue",
    )

    with pytest.raises(ValueError, match="clip start"):
        span.clip(revenue, start=date(2025, 2, 1), end=date(2025, 1, 1))


def test_span_map_decorator_uses_value_formula_and_period():
    revenue = span.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), 100.0),
            ((date(2025, 2, 1), date(2025, 3, 1)), 200.0),
        ],
        agg=sum_spans(0.0),
        label="Revenue",
    )

    @span.map(revenue, label="RevenuePlusDays")
    def revenue_plus_days(
        period: Period,
        value: Formula[float | None],
    ) -> Formula[float | None]:
        days = float((period.end - period.start).days)
        return value.map(lambda amount: None if amount is None else amount + days)

    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 3, 1))

    assert revenue_plus_days.label == "RevenuePlusDays"
    assert revenue_plus_days.value(ctx, period).eval() == pytest.approx(359.0)


def test_span_map_recomputes_period_dependent_formula_after_split():
    revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 310.0)],
        agg=sum_spans(0.0),
        split=split_daily,
        label="Revenue",
    )

    @span.map(revenue)
    def daily_revenue(
        period: Period,
        value: Formula[float | None],
    ) -> Formula[float | None]:
        days = float((period.end - period.start).days)
        return value.map(lambda amount: None if amount is None else amount / days)

    ctx = Context()
    period = Period(date(2025, 1, 11), date(2025, 1, 21))

    assert daily_revenue.label == "daily_revenue"
    assert daily_revenue.value(ctx, period).eval() == pytest.approx(10.0)


def test_span_map_accepts_lazy_span_series_ref():
    calls = 0
    revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        label="Revenue",
    )

    def revenue_ref() -> span.SpanSeriesDef:
        nonlocal calls
        calls += 1
        return revenue

    @span.map(revenue_ref)
    def doubled(
        period: Period,
        value: Formula[float | None],
    ) -> Formula[float | None]:
        return value.map(lambda amount: None if amount is None else amount * 2.0)

    assert doubled.label == "doubled"
    assert calls == 0

    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 2, 1))
    assert doubled.value(ctx, period).eval() == pytest.approx(200.0)
    assert doubled.value(ctx, period).eval() == pytest.approx(200.0)
    assert calls == 1


def test_span_series_fluent_helpers_compose_existing_constructors():
    revenue = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 310.0)],
        agg=sum_spans(0.0),
        split=split_daily,
        label="Revenue",
    )

    @revenue.map(label="DailyRevenue")
    def daily_revenue(
        period: Period,
        value: Formula[float | None],
    ) -> Formula[float | None]:
        days = float((period.end - period.start).days)
        return value.map(lambda amount: None if amount is None else amount / days)

    clipped_scaled = daily_revenue.clip(
        start=date(2025, 1, 11),
        end=date(2025, 1, 21),
    ).scale(2.0)

    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 2, 1))

    assert daily_revenue.label == "DailyRevenue"
    assert clipped_scaled.value(ctx, period).eval() == pytest.approx(20.0)


def test_span_series_then_clips_continuation_to_base_end():
    historical = span.from_list(
        [((date(2025, 1, 1), date(2025, 3, 1)), 100.0)],
        agg=sum_spans(0.0),
        label="Historical",
    )
    projected = span.from_list(
        [((date(2025, 2, 15), date(2025, 3, 15)), 28.0)],
        agg=sum_spans(0.0),
        split=split_daily,
        label="Projected",
    )

    revenue = historical.then(projected, label="Revenue")
    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 4, 1))
    spans = revenue.query(ctx, period).eval()

    assert revenue.label == "Revenue"
    assert [span_cell.period for span_cell in spans] == [
        Period(date(2025, 1, 1), date(2025, 3, 1)),
        Period(date(2025, 3, 1), date(2025, 3, 15)),
        Period(date(2025, 3, 15), date(2025, 4, 1)),
    ]
    values = [span_cell.eval(ctx) for span_cell in spans]
    assert values[:2] == pytest.approx([100.0, 14.0])
    assert values[2] is None


def test_span_series_then_uses_unclipped_continuation_when_base_is_empty():
    historical = span.from_list([], agg=sum_spans(0.0), label="Historical")
    projected = span.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 100.0)],
        agg=sum_spans(0.0),
        label="Projected",
    )

    revenue = historical.then(projected)
    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 2, 1))

    assert revenue.label == "Historical"
    assert revenue.value(ctx, period).eval() == pytest.approx(100.0)


def test_structurally_equal_defs_have_distinct_context_caches():
    calls: list[str] = []

    def spans(ctx: Context):
        calls.append("called")
        yield from ()

    agg = sum_spans(0.0)
    left = span.SpanSeriesDef(fn=spans, agg=agg, label="Same")
    right = span.SpanSeriesDef(fn=spans, agg=agg, label="Same")

    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 2, 1))
    left.query(ctx, period).eval()
    right.query(ctx, period).eval()

    assert left == right
    assert left is not right
    assert calls == ["called", "called"]
