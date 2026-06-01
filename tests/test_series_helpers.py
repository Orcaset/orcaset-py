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
