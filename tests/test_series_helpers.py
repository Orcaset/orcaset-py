from datetime import date
from typing import Iterable

import pytest

from orcaset import (
    Context,
    Formula,
    Period,
    PointSeries,
    Span,
    SpanSeries,
    align_spans,
    avg_spans,
    no_split,
    split_const,
    split_daily,
    sum_spans,
)
from orcaset.yf import YF


def eval_spans(ctx: Context, spans: list[Span]) -> list[float | None]:
    return [span.eval(ctx) for span in spans]


def test_span_aggregation_helpers_fill_none_values():
    class Revenue(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 2, 1)),
                Formula.pure(310.0),
                no_split,
            )
            yield Span(
                Period(date(2025, 2, 1), date(2025, 3, 1)),
                Formula.pure(None),
                no_split,
            )

    ctx = Context()
    spans = ctx.get(Revenue).query(Period(date(2025, 1, 1), date(2025, 3, 1))).eval()

    assert sum_spans(5.0)(spans) == 315.0
    assert avg_spans(YF.act360, 5.0)(spans) == pytest.approx((310.0 * 31 + 5.0 * 28) / 59)


def test_point_series_operator_constructors():
    class A(PointSeries):
        def point(self, dt: date) -> Formula[float | None]:
            return Formula.pure(10.0)

    class B(PointSeries):
        def point(self, dt: date) -> Formula[float | None]:
            return Formula.pure(2.0 if dt == date(2025, 1, 1) else None)

    ctx = Context()
    dt = date(2025, 1, 1)

    assert ctx.get(PointSeries.neg(A)).query(dt).eval().eval(ctx) == -10.0
    assert ctx.get(PointSeries.scale(A, 3.0)).query(dt).eval().eval(ctx) == 30.0
    assert ctx.get(PointSeries.sum([A, B])).query(dt).eval().eval(ctx) == 12.0
    assert ctx.get(PointSeries.sub(A, B)).query(dt).eval().eval(ctx) == 8.0
    assert ctx.get(PointSeries.mul([A, B])).query(dt).eval().eval(ctx) == 20.0
    assert ctx.get(PointSeries.div(A, B)).query(dt).eval().eval(ctx) == 5.0


def test_point_series_accumulate_sums_span_changes():
    Changes = SpanSeries.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), 310.0),
            ((date(2025, 2, 1), date(2025, 3, 1)), 280.0),
        ],
        split=split_daily,
        name="Changes",
    )
    Balance = PointSeries.accumulate(
        start=date(2025, 1, 1),
        value=1000.0,
        changes=Changes,
        name="Balance",
    )

    ctx = Context()
    balance = ctx.get(Balance)

    assert balance.query(date(2024, 12, 31)).eval().eval(ctx) is None
    assert balance.query(date(2025, 1, 1)).eval().eval(ctx) == 1000.0
    assert balance.query(date(2025, 1, 11)).eval().eval(ctx) == pytest.approx(1100.0)
    assert balance.query(date(2025, 2, 1)).eval().eval(ctx) == pytest.approx(1310.0)
    assert balance.query(date(2025, 3, 1)).eval().eval(ctx) == pytest.approx(1590.0)


def test_point_series_accumulate_treats_none_changes_as_zero():
    Changes = SpanSeries.from_list(
        [
            ((date(2025, 1, 1), date(2025, 2, 1)), None),
            ((date(2025, 2, 1), date(2025, 3, 1)), 280.0),
        ],
        name="Changes",
    )
    Balance = PointSeries.accumulate(
        start=date(2025, 1, 1),
        value=1000.0,
        changes=Changes,
        name="Balance",
    )

    ctx = Context()
    balance = ctx.get(Balance)

    assert balance.query(date(2025, 3, 1)).eval().eval(ctx) == pytest.approx(1280.0)


def test_point_series_accumulate_none_start_value_stays_none():
    Changes = SpanSeries.from_list(
        [((date(2025, 1, 1), date(2025, 2, 1)), 310.0)],
        name="Changes",
    )
    Balance = PointSeries.accumulate(
        start=date(2025, 1, 1),
        value=None,
        changes=Changes,
        name="Balance",
    )

    ctx = Context()
    balance = ctx.get(Balance)

    assert balance.query(date(2025, 1, 1)).eval().eval(ctx) is None
    assert balance.query(date(2025, 2, 1)).eval().eval(ctx) is None


def test_span_series_sum_aligns_by_dates_not_index():
    class A(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 3, 1)),
                Formula.pure(590.0),
                split_daily,
            )

    class B(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 15), date(2025, 2, 15)),
                Formula.pure(310.0),
                split_daily,
            )

    ctx = Context()
    summed = ctx.get(SpanSeries.sum([A, B]))
    spans = summed.query(Period(date(2025, 1, 1), date(2025, 3, 1))).eval()

    assert [span.period for span in spans] == [
        Period(date(2025, 1, 1), date(2025, 1, 15)),
        Period(date(2025, 1, 15), date(2025, 2, 15)),
        Period(date(2025, 2, 15), date(2025, 3, 1)),
    ]
    assert eval_spans(ctx, spans) == [None, 620.0, None]

    partial = summed.query(Period(date(2025, 1, 20), date(2025, 1, 25))).eval()
    assert [span.period for span in partial] == [Period(date(2025, 1, 20), date(2025, 1, 25))]
    assert eval_spans(ctx, partial) == pytest.approx([100.0])


def test_span_series_operator_constructors():
    class A(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 2, 1)),
                Formula.pure(10.0),
                split_daily,
            )

    class B(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 2, 1)),
                Formula.pure(2.0),
                split_daily,
            )

    ctx = Context()
    period = Period(date(2025, 1, 1), date(2025, 2, 1))

    assert eval_spans(ctx, ctx.get(SpanSeries.neg(A)).query(period).eval()) == [-10.0]
    assert eval_spans(ctx, ctx.get(SpanSeries.scale(A, 3.0)).query(period).eval()) == [30.0]
    assert eval_spans(ctx, ctx.get(SpanSeries.sub(A, B)).query(period).eval()) == [8.0]
    assert eval_spans(ctx, ctx.get(SpanSeries.mul([A, B])).query(period).eval()) == [20.0]
    assert eval_spans(ctx, ctx.get(SpanSeries.div(A, B)).query(period).eval()) == [5.0]


def test_split_const_preserves_source_value_on_both_sides():
    class Rate(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 2, 1)),
                Formula.pure(7.5),
                split_const,
            )

    ctx = Context()
    spans = ctx.get(Rate).query(Period(date(2025, 1, 11), date(2025, 1, 21))).eval()

    assert [span.period for span in spans] == [Period(date(2025, 1, 11), date(2025, 1, 21))]
    assert eval_spans(ctx, spans) == [7.5]


def test_align_spans_returns_none_spans_for_missing_inputs():
    class A(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 1, 11)),
                Formula.pure(10.0),
                split_daily,
            )

    class B(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 6), date(2025, 1, 11)),
                Formula.pure(20.0),
                split_daily,
            )

    ctx = Context()
    aligned = list(align_spans([ctx.get(A), ctx.get(B)]))

    assert [[span.period for span in row] for row in aligned] == [
        [Period(date(2025, 1, 1), date(2025, 1, 6))] * 2,
        [Period(date(2025, 1, 6), date(2025, 1, 11))] * 2,
    ]
    assert [[span.eval(ctx) for span in row] for row in aligned] == [
        [5.0, None],
        [5.0, 20.0],
    ]


def test_align_spans_requires_series_from_same_context():
    class A(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 1, 11)),
                Formula.pure(10.0),
                no_split,
            )

    with pytest.raises(ValueError, match="same Context"):
        list(align_spans([Context().get(A), Context().get(A)]))


def test_span_series_extend_continues_after_base_end():
    class Base(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 3, 1)),
                Formula.pure(590.0),
                split_daily,
            )

    @SpanSeries.extend(Base)
    def Extended(_: SpanSeries, start: date | None) -> Iterable[Span]:
        assert start == date(2025, 3, 1)
        yield Span(
            Period(date(2025, 3, 1), date(2025, 4, 1)),
            Formula.pure(620.0),
            no_split,
        )

    ctx = Context()
    extended = ctx.get(Extended)
    spans = extended.query(Period(date(2025, 1, 1), date(2025, 4, 1))).eval()

    assert [span.period for span in spans] == [
        Period(date(2025, 1, 1), date(2025, 3, 1)),
        Period(date(2025, 3, 1), date(2025, 4, 1)),
    ]
    assert eval_spans(ctx, spans) == pytest.approx([590.0, 620.0])


def test_span_series_extend_passes_none_to_continuation_for_empty_base():
    class Base(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield from ()

    @SpanSeries.extend(Base)
    def Extended(_: SpanSeries, start: date | None) -> Iterable[Span]:
        assert start is None
        yield Span(
            Period(date(2025, 1, 1), date(2025, 2, 1)),
            Formula.pure(620.0),
            no_split,
        )

    ctx = Context()
    extended = ctx.get(Extended)
    spans = extended.query(Period(date(2025, 1, 1), date(2025, 2, 1))).eval()

    assert [span.period for span in spans] == [
        Period(date(2025, 1, 1), date(2025, 2, 1)),
    ]
    assert eval_spans(ctx, spans) == pytest.approx([620.0])


def test_span_series_extend_continuation_can_query_base_spans_on_self():
    class Base(SpanSeries):
        def spans(self) -> Iterable[Span]:
            yield Span(
                Period(date(2025, 1, 1), date(2025, 2, 1)),
                Formula.pure(100.0),
                no_split,
            )

    @SpanSeries.extend(Base)
    def Extended(series: SpanSeries, start: date | None) -> Iterable[Span]:
        assert start == date(2025, 2, 1)
        prior = series.query(Period(date(2025, 1, 1), date(2025, 2, 1)))
        yield Span(
            Period(date(2025, 2, 1), date(2025, 3, 1)),
            prior.map(
                lambda spans: sum(span.eval(series.ctx) or 0.0 for span in spans) + 10.0
            ),
            no_split,
        )

    ctx = Context()
    extended = ctx.get(Extended)
    spans = extended.query(Period(date(2025, 1, 1), date(2025, 3, 1))).eval()

    assert [span.period for span in spans] == [
        Period(date(2025, 1, 1), date(2025, 2, 1)),
        Period(date(2025, 2, 1), date(2025, 3, 1)),
    ]
    assert eval_spans(ctx, spans) == pytest.approx([100.0, 110.0])
